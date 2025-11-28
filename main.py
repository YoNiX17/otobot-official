import discord
from discord import app_commands
from discord.ext import commands
import wavelink
import logging
import os
import datetime

# --- CONFIGURATION ---
LAVALINK_URI = os.getenv("LAVALINK_URI", "lavalink2-production-82e6.up.railway.app")
LAVALINK_PASS = os.getenv("LAVALINK_PASS", "youshallnotpass")
HTTPS_ENABLED = os.getenv("HTTPS_ENABLED", "True").lower() == "true"

logging.basicConfig(level=logging.INFO)

# --- UTILITAIRES ---
def format_time(milliseconds):
    """Convertit les ms en format mm:ss"""
    seconds = int(milliseconds / 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def create_progress_bar(position, duration, length=20):
    """Crée une barre de progression visuelle"""
    if duration == 0: return "🔘" + "▬" * length
    percentage = position / duration
    filled = int(percentage * length)
    empty = length - filled
    return "▬" * filled + "🔘" + "▬" * empty

# --- COMPOSANTS D'INTERFACE ---

class FilterSelect(discord.ui.Select):
    def __init__(self, player: wavelink.Player):
        options = [
            discord.SelectOption(label="Aucun Effet", description="Son normal", emoji="💿", value="none"),
            discord.SelectOption(label="Bass Boost", description="Pour les grosses basses", emoji="💥", value="bass"),
            discord.SelectOption(label="Nightcore", description="Plus rapide et aigu", emoji="🐱", value="nightcore"),
            discord.SelectOption(label="Vaporwave", description="Lent et esthétique", emoji="🌴", value="vaporwave"),
            discord.SelectOption(label="8D Audio", description="Son rotatif", emoji="🎧", value="8d"),
        ]
        super().__init__(placeholder="🎛️ Choisir un effet audio...", min_values=1, max_values=1, options=options, row=0)
        self.player = player

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        filters: wavelink.Filters = self.player.filters
        filters.reset() # Reset des anciens filtres

        if value == "bass":
            filters.equalizer.set(band=0, gain=0.3)
            filters.equalizer.set(band=1, gain=0.2)
        elif value == "nightcore":
            filters.timescale.set(pitch=1.2, speed=1.1)
        elif value == "vaporwave":
            filters.timescale.set(pitch=0.8, speed=0.85)
        elif value == "8d":
            filters.rotation.set(rotation_hz=0.2)
        
        await self.player.set_filters(filters)
        await interaction.response.send_message(f"🎛️ **Filtre appliqué :** {self.options[self.options.index(next(o for o in self.options if o.value == value))].label}", ephemeral=True)

class MusicControls(discord.ui.View):
    def __init__(self, player: wavelink.Player):
        super().__init__(timeout=None)
        self.player = player
        # On ajoute le menu déroulant en haut
        self.add_item(FilterSelect(player))

    # --- LIGNE 1 : Contrôles de lecture ---
    
    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=1)
    async def restart(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.seek(0)
        await interaction.response.send_message("⏮️ **Recommencé**", ephemeral=True)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, row=1)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player.paused:
            await self.player.pause(False)
            button.style = discord.ButtonStyle.green
        else:
            await self.player.pause(True)
            button.style = discord.ButtonStyle.red
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, row=1)
    async def stop_music(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.queue.clear() # On vide la file pour être sûr
        await self.player.disconnect()
        await interaction.response.send_message("👋 **Fermeture du lecteur**", ephemeral=True)
        self.stop()

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=1)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Skip Robuste : On force la lecture du suivant manuellement
        if not self.player.queue.is_empty:
            next_track = self.player.queue.get()
            await self.player.play(next_track)
            await interaction.response.send_message(f"⏭️ **Passé :** {next_track.title}", ephemeral=True)
        else:
            await self.player.stop()
            await interaction.response.send_message("⏭️ **Fin de la file.**", ephemeral=True)

    # --- LIGNE 2 : Options (Volume, Queue, Loop) ---

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, row=2)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_vol = max(0, self.player.volume - 10)
        await self.player.set_volume(new_vol)
        await interaction.response.send_message(f"🔉 Volume : **{new_vol}%**", ephemeral=True)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, row=2)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_vol = min(100, self.player.volume + 10)
        await self.player.set_volume(new_vol)
        await interaction.response.send_message(f"🔊 Volume : **{new_vol}%**", ephemeral=True)

    @discord.ui.button(emoji="🔂", style=discord.ButtonStyle.secondary, row=2)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player.queue.mode == wavelink.QueueMode.normal:
            self.player.queue.mode = wavelink.QueueMode.loop
            button.style = discord.ButtonStyle.green
            await interaction.response.send_message("🔂 **Boucle : Piste**", ephemeral=True)
        elif self.player.queue.mode == wavelink.QueueMode.loop:
            self.player.queue.mode = wavelink.QueueMode.loop_all
            button.style = discord.ButtonStyle.blurple
            button.emoji = "🔁"
            await interaction.response.send_message("🔁 **Boucle : File**", ephemeral=True)
        else:
            self.player.queue.mode = wavelink.QueueMode.normal
            button.style = discord.ButtonStyle.secondary
            button.emoji = "➡️"
            await interaction.response.send_message("➡️ **Boucle : Désactivée**", ephemeral=True)
        await interaction.message.edit(view=self)

    @discord.ui.button(emoji="📜", label="Voir la File", style=discord.ButtonStyle.gray, row=2)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.player.queue:
            return await interaction.response.send_message("📭 La file est vide.", ephemeral=True)
        
        queue_text = ""
        for i, track in enumerate(self.player.queue[:10]):
            queue_text += f"`{i+1}.` **{track.title}** ({format_time(track.length)})\n"
        
        embed = discord.Embed(title=f"📜 File d'attente ({len(self.player.queue)})", description=queue_text, color=0x2b2d31)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- BOT PRINCIPAL ---
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
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="de la musique"))
        try:
            await self.tree.sync()
            print("🔄 Commandes synchronisées.")
        except Exception as e:
            print(f"Erreur synchro: {e}")

    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"✅ Node Lavalink EN LIGNE : {payload.node.identifier}")

    # --- CONSTRUCTION DE L'INTERFACE COMPLEXE ---
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if not player: return
        track = payload.track
        
        # Calcul des infos
        duration = format_time(track.length)
        bar = create_progress_bar(0, track.length)
        
        # Embed Principal (Style Dark / Moderne)
        embed = discord.Embed(color=0x5865F2) # Bleu Discord ou 0x000000 pour full black
        
        # Auteur et Icône
        embed.set_author(name=f"Lecture en cours sur {player.channel.name}", icon_url="https://i.imgur.com/5s5y8bO.gif") # Petit gif d'equalizer
        
        # Titre et Lien
        embed.title = track.title[:256]
        embed.url = track.uri
        
        # Description : Barre de progression + Temps
        embed.description = f"{bar}\n\n`00:00` / `{duration}`"
        
        # Champs d'info (Grid layout)
        embed.add_field(name="👤 Artiste", value=f"**{track.author}**", inline=True)
        embed.add_field(name="💿 Source", value=f"`{track.source.capitalize()}`", inline=True)
        
        # Info Prochaine musique
        if not player.queue.is_empty:
            next_track = player.queue[0]
            embed.add_field(name="🔜 À suivre", value=f"{next_track.title}", inline=False)
        else:
            embed.add_field(name="🔜 À suivre", value="*Fin de la liste*", inline=False)

        # Image (Album Art) en Grand
        if track.artwork: 
            embed.set_image(url=track.artwork)
        
        # Footer technique
        embed.set_footer(text=f"Volume: {player.volume}% • Effets: Aucun • OtoBot v2.0", icon_url=self.user.display_avatar.url)

        view = MusicControls(player)
        await player.home.send(embed=embed, view=view)

    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player: return
        
        # Logique Intelligente :
        # On ne joue la suivante automatiquement QUE si la musique est finie naturellement (FINISHED).
        # Si on a cliqué sur SKIP (REPLACED) ou STOP (STOPPED), on laisse les boutons gérer ça.
        if payload.reason == "FINISHED":
            if not player.queue.is_empty:
                await player.play(player.queue.get())

bot = MusicBot()

# --- COMMANDES SLASH ---

@bot.tree.command(name="play", description="Joue une musique (YouTube, Spotify...)")
@app_commands.describe(recherche="Titre ou lien")
async def play(interaction: discord.Interaction, recherche: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ Connecte-toi d'abord !", ephemeral=True)
    
    if not wavelink.Pool.get_node():
        return await interaction.response.send_message("❌ Le système audio démarre...", ephemeral=True)

    await interaction.response.defer()

    if not interaction.guild.voice_client:
        try:
            vc = await interaction.user.voice.channel.connect(cls=wavelink.Player)
        except:
            return await interaction.followup.send("❌ Impossible de rejoindre.")
    else:
        vc = interaction.guild.voice_client

    vc.home = interaction.channel
    vc.autoplay = wavelink.AutoPlayMode.partial

    try:
        tracks = await wavelink.Playable.search(recherche)
    except Exception as e:
        return await interaction.followup.send(f"❌ Erreur : {e}")

    if not tracks:
        return await interaction.followup.send("❌ Rien trouvé.")

    if isinstance(tracks, wavelink.Playlist):
        await vc.queue.put_wait(tracks)
        embed = discord.Embed(description=f"✅ **Playlist ajoutée :** {tracks.name} (`{len(tracks)}` sons)", color=0x43b581)
        await interaction.followup.send(embed=embed)
    else:
        track = tracks[0]
        await vc.queue.put_wait(track)
        embed = discord.Embed(description=f"✅ **Ajouté :** [{track.title}]({track.uri})", color=0x43b581)
        if track.artwork: embed.set_thumbnail(url=track.artwork)
        await interaction.followup.send(embed=embed)
        
    if not vc.playing:
        await vc.play(vc.queue.get())

@bot.tree.command(name="stop", description="Stop le bot")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("👋 Ciao !")
    else:
        await interaction.response.send_message("❌ Pas connecté.", ephemeral=True)

@bot.tree.command(name="volume", description="Régler le volume")
async def volume(interaction: discord.Interaction, niveau: int):
    vc = interaction.guild.voice_client
    if vc:
        await vc.set_volume(max(0, min(100, niveau)))
        await interaction.response.send_message(f"🔊 Volume : {vc.volume}%")

# Lancement
token = os.getenv('DISCORD_TOKEN')
if not token:
    print("❌ ERREUR : Variable DISCORD_TOKEN manquante")
else:
    bot.run(token)
