import discord
from discord import app_commands
from discord.ext import commands
import wavelink
import logging
import os
import asyncio

# --- CONFIGURATION ---
LAVALINK_URI = os.getenv("LAVALINK_URI", "lavalink2-production-82e6.up.railway.app")
LAVALINK_PASS = os.getenv("LAVALINK_PASS", "youshallnotpass")
HTTPS_ENABLED = os.getenv("HTTPS_ENABLED", "True").lower() == "true"

logging.basicConfig(level=logging.INFO)

# --- CLASSE DES BOUTONS DE CONTRÔLE ---
class MusicControls(discord.ui.View):
    def __init__(self, player: wavelink.Player):
        super().__init__(timeout=None)
        self.player = player

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.blurple)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player.paused:
            await self.player.pause(False)
            button.style = discord.ButtonStyle.green
            await interaction.response.send_message("▶️ Musique relancée.", ephemeral=True)
        else:
            await self.player.pause(True)
            button.style = discord.ButtonStyle.red
            await interaction.response.send_message("⏸️ Musique en pause.", ephemeral=True)
        await interaction.message.edit(view=self)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.skip(force=True)
        await interaction.response.send_message("⏭️ Musique passée.", ephemeral=True)

    # CORRECTION ICI : J'ai renommé la fonction 'stop' en 'stop_music'
    # Cela évite le conflit avec la méthode self.stop() native de Discord.ui
    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_music(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.disconnect()
        await interaction.response.send_message("👋 Déconnexion.", ephemeral=True)
        self.stop() # Maintenant, ceci appelle bien la fonction pour arrêter les boutons

    @discord.ui.button(emoji="🔂", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player.queue.mode == wavelink.QueueMode.normal:
            self.player.queue.mode = wavelink.QueueMode.loop
            button.style = discord.ButtonStyle.green
            await interaction.response.send_message("🔂 Mode boucle activé.", ephemeral=True)
        else:
            self.player.queue.mode = wavelink.QueueMode.normal
            button.style = discord.ButtonStyle.secondary
            await interaction.response.send_message("➡️ Mode boucle désactivé.", ephemeral=True)
        await interaction.message.edit(view=self)


# --- BOT ---
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        nodes = [
            wavelink.Node(
                uri=f"https://{LAVALINK_URI}:443" if HTTPS_ENABLED else f"http://{LAVALINK_URI}:2333", 
                password=LAVALINK_PASS
            )
        ]
        await wavelink.Pool.connect(nodes=nodes, client=self, cache_capacity=100)
        print(f"✅ Tentative de connexion à Lavalink sur {LAVALINK_URI}...")

    async def on_ready(self):
        print(f'🤖 Connecté en tant que {self.user} (ID: {self.user.id})')
        try:
            synced = await self.tree.sync()
            print(f"🔄 {len(synced)} commandes slash synchronisées.")
        except Exception as e:
            print(f"Erreur de synchro : {e}")

    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"✅ Node Lavalink EN LIGNE : {payload.node.identifier}")

    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if not player: return
        track = payload.track
        
        embed = discord.Embed(
            title="🎶 Lecture en cours",
            description=f"**[{track.title}]({track.uri})**",
            color=discord.Color.from_rgb(29, 185, 84)
        )
        embed.add_field(name="Artiste", value=track.author, inline=True)
        
        duration_min = track.length // 60000
        duration_sec = (track.length % 60000) // 1000
        embed.add_field(name="Durée", value=f"{duration_min}:{duration_sec:02d}", inline=True)
        if track.artwork: embed.set_thumbnail(url=track.artwork)
        
        view = MusicControls(player)
        await player.home.send(embed=embed, view=view)

bot = MusicBot()

# --- COMMANDES SLASH ---
@bot.tree.command(name="play", description="Joue une musique")
@app_commands.describe(recherche="Lien ou nom")
async def play(interaction: discord.Interaction, recherche: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ Connecte-toi d'abord en vocal !", ephemeral=True)
    if not wavelink.Pool.get_node():
        return await interaction.response.send_message("❌ Lavalink n'est pas encore prêt.", ephemeral=True)

    await interaction.response.defer()

    if not interaction.guild.voice_client:
        vc = await interaction.user.voice.channel.connect(cls=wavelink.Player)
    else:
        vc = interaction.guild.voice_client

    vc.home = interaction.channel

    try:
        tracks = await wavelink.Playable.search(recherche)
    except Exception as e:
        return await interaction.followup.send(f"❌ Erreur : {e}")

    if not tracks:
        return await interaction.followup.send("❌ Rien trouvé.")

    if isinstance(tracks, wavelink.Playlist):
        await vc.queue.put_wait(tracks)
        response = f"✅ Playlist **{tracks.name}** ajoutée."
    else:
        track = tracks[0]
        await vc.queue.put_wait(track)
        response = f"✅ **{track.title}** ajouté."
        
    if not vc.playing:
        await vc.play(vc.queue.get())

    await interaction.followup.send(response)

@bot.tree.command(name="stop", description="Stop et déconnexion")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("👋 Au revoir.")
    else:
        await interaction.response.send_message("❌ Je ne suis pas connecté.", ephemeral=True)

@bot.tree.command(name="skip", description="Suivant")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.playing:
        await vc.skip(force=True)
        await interaction.response.send_message("⏭️ Suivant.")
    else:
        await interaction.response.send_message("❌ Rien à passer.", ephemeral=True)

token = os.getenv('DISCORD_TOKEN')
if not token:
    print("❌ ERREUR : Variable DISCORD_TOKEN manquante")
else:
    bot.run(token)
