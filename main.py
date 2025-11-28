import discord
from discord import app_commands
from discord.ext import commands
import wavelink
import logging

# --- CONFIGURATION ---
LAVALINK_URI = "lavalink2-lcko.onrender.com" # Ton serveur Render
LAVALINK_PASS = "youshallnotpass"            # Ton mot de passe défini dans application.yml
HTTPS_ENABLED = True                         # Render utilise HTTPS (Port 443)

# Configuration des logs pour voir ce qui se passe
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

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.disconnect()
        await interaction.response.send_message("👋 Déconnexion.", ephemeral=True)
        self.stop()

    @discord.ui.button(emoji="🔂", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Inverse le mode loop
        if self.player.queue.mode == wavelink.QueueMode.normal:
            self.player.queue.mode = wavelink.QueueMode.loop
            button.style = discord.ButtonStyle.green
            await interaction.response.send_message("🔂 Mode boucle activé.", ephemeral=True)
        else:
            self.player.queue.mode = wavelink.QueueMode.normal
            button.style = discord.ButtonStyle.secondary
            await interaction.response.send_message("➡️ Mode boucle désactivé.", ephemeral=True)
        await interaction.message.edit(view=self)


# --- CLASSE PRINCIPALE DU BOT ---
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Connexion à Lavalink au démarrage
        nodes = [
            wavelink.Node(
                uri=f"https://{LAVALINK_URI}:443" if HTTPS_ENABLED else f"http://{LAVALINK_URI}:2333", 
                password=LAVALINK_PASS
            )
        ]
        await wavelink.Pool.connect(nodes=nodes, client=self, cache_capacity=100)
        print("✅ Connecté à Lavalink !")

    async def on_ready(self):
        print(f'🤖 Connecté en tant que {self.user} (ID: {self.user.id})')
        # Synchronisation des commandes slash (peut prendre jusqu'à 1h globalement, mais instantané sur ton serveur de dev)
        try:
            synced = await self.tree.sync()
            print(f"🔄 {len(synced)} commandes slash synchronisées.")
        except Exception as e:
            print(f"Erreur de synchro : {e}")

    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"Node Lavalink prêt : {payload.node.identifier}")

    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if not player:
            return

        track = payload.track
        
        # Création de l'interface "Belle" (Embed)
        embed = discord.Embed(
            title="🎶 Lecture en cours",
            description=f"**[{track.title}]({track.uri})**",
            color=discord.Color.from_rgb(29, 185, 84) # Vert Spotify
        )
        embed.add_field(name="Artiste", value=track.author, inline=True)
        
        # Gestion de la durée (ms -> min:sec)
        duration_min = track.length // 60000
        duration_sec = (track.length % 60000) // 1000
        embed.add_field(name="Durée", value=f"{duration_min}:{duration_sec:02d}", inline=True)
        
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        
        embed.set_footer(text=f"Source : {track.source}")

        # Envoi du message avec les boutons
        view = MusicControls(player)
        await player.home.send(embed=embed, view=view)


bot = MusicBot()


# --- COMMANDES SLASH (/) ---

@bot.tree.command(name="play", description="Joue une musique depuis YouTube ou Spotify")
@app_commands.describe(recherche="Lien ou nom de la musique")
async def play(interaction: discord.Interaction, recherche: str):
    """Joue une musique."""
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ Tu dois être dans un canal vocal !", ephemeral=True)

    await interaction.response.defer() # Donne du temps au bot pour chercher

    # Connexion au vocal si nécessaire
    if not interaction.guild.voice_client:
        vc: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
    else:
        vc: wavelink.Player = interaction.guild.voice_client

    # On définit le canal textuel pour envoyer les messages "Now Playing"
    vc.home = interaction.channel

    # Recherche de la musique (Gère Spotify et YouTube grâce à LavaSrc côté serveur)
    try:
        tracks = await wavelink.Playable.search(recherche)
    except Exception as e:
        return await interaction.followup.send(f"❌ Erreur lors de la recherche : {e}")

    if not tracks:
        return await interaction.followup.send("❌ Aucune musique trouvée.")

    # Gestion Playlist vs Musique seule
    if isinstance(tracks, wavelink.Playlist):
        added = await vc.queue.put_wait(tracks)
        response = f"✅ Ajout de la playlist **{tracks.name}** ({added} musiques) à la file."
        first_track = tracks[0]
    else:
        track = tracks[0]
        await vc.queue.put_wait(track)
        response = f"✅ Ajouté à la file : **{track.title}**"
        
    if not vc.playing:
        await vc.play(vc.queue.get())

    await interaction.followup.send(response)


@bot.tree.command(name="skip", description="Passe à la musique suivante")
async def skip(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client
    if vc and vc.playing:
        await vc.skip(force=True)
        await interaction.response.send_message("⏭️ Musique passée.")
    else:
        await interaction.response.send_message("❌ Rien ne joue actuellement.", ephemeral=True)


@bot.tree.command(name="stop", description="Arrête la musique et déconnecte le bot")
async def stop(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("👋 Ciao !")
    else:
        await interaction.response.send_message("❌ Je ne suis pas connecté.", ephemeral=True)


@bot.tree.command(name="volume", description="Change le volume (0-100)")
async def volume(interaction: discord.Interaction, niveau: int):
    vc: wavelink.Player = interaction.guild.voice_client
    if vc:
        # Limite de sécurité 0-100
        vol = max(0, min(100, niveau))
        await vc.set_volume(vol)
        await interaction.response.send_message(f"🔊 Volume réglé sur {vol}%")
    else:
        await interaction.response.send_message("❌ Je ne suis pas connecté.", ephemeral=True)

# Lancer le bot
# REMPLACE 'TON_TOKEN_ICI' PAR LE VRAI TOKEN DE TON BOT DISCORD
bot.run('MTM4MzgzMTQ5ODM3NzAwNzE4NQ.GV8Zlw.KPBAynpJUEMBsD9UXnphEUT0mAliiPhciAJt2A')
