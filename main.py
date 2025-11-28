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
    return f"{minutes:02d}:{seconds:02d}"

def create_progress_bar(position, duration, length=15):
    """Crée une barre de progression visuelle"""
    if duration == 0: return "🔘" + "▬" * length
    percentage = position / duration
    filled = int(percentage * length)
    empty = length - filled
    return "▬" * filled + "🔘" + "▬" * empty

# --- INTERFACE (BOUTONS) ---
class MusicControls(discord.ui.View):
    def __init__(self, player: wavelink.Player):
        super().__init__(timeout=None)
        self.player = player

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.blurple)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player.paused:
            await self.player.pause(False)
            button.style = discord.ButtonStyle.green
            await interaction.response.send_message("▶️ **Lecture reprise**", ephemeral=True)
        else:
            await self.player.pause(True)
            button.style = discord.ButtonStyle.red
            await interaction.response.send_message("⏸️ **En pause**", ephemeral=True)
        await interaction.message.edit(view=self)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏭️ **Musique passée**", ephemeral=True)
        await self.player.skip(force=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_music(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player.disconnect()
        await interaction.response.send_message("👋 **Arrêt et déconnexion**", ephemeral=True)
        self.stop()

    @discord.ui.button(emoji="🔂", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player.queue.mode == wavelink.QueueMode.normal:
            self.player.queue.mode = wavelink.QueueMode.loop
            button.style = discord.ButtonStyle.green
            button.emoji = "🔂"
            await interaction.response.send_message("🔂 **Mode boucle : Activé** (Cette musique)", ephemeral=True)
        elif self.player.queue.mode == wavelink.QueueMode.loop:
            self.player.queue.mode = wavelink.QueueMode.loop_all
            button.style = discord.ButtonStyle.primary
            button.emoji = "🔁"
            await interaction.response.send_message("🔁 **Mode boucle : File d'attente**", ephemeral=True)
        else:
            self.player.queue.mode = wavelink.QueueMode.normal
            button.style = discord.ButtonStyle.secondary
            button.emoji = "➡️"
            await interaction.response.send_message("➡️ **Mode boucle : Désactivé**", ephemeral=True)
        await interaction.message.edit(view=self)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.gray, label="File")
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Affiche la file d'attente via un bouton"""
        if not self.player.queue:
            return await interaction.response.send_message("La file d'attente est vide.", ephemeral=True)
        
        queue_list = ""
        for i, track in enumerate(self.player.queue[:10]): # Affiche max 10
            queue_list += f"`{i+1}.` {track.title} - *{track.author}*\n"
        
        remaining = len(self.player.queue) - 10
        if remaining > 0:
            queue_list += f"\n*...et {remaining} autres.*"

        embed = discord.Embed(title="📜 File d'attente", description=queue_list, color=discord.Color.blurple())
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
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/play"))
        try:
            synced = await self.tree.sync()
            print(f"🔄 {len(synced)} commandes slash synchronisées.")
        except Exception as e:
            print(f"Erreur de synchro : {e}")

    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"✅ Node Lavalink EN LIGNE : {payload.node.identifier}")

    # --- ÉVÉNEMENTS DE LECTURE ---
    
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        """Déclenché quand une musique commence"""
        player = payload.player
        if not player: return
        track = payload.track
        
        embed = discord.Embed(
            description=f"## [{track.title}]({track.uri})",
            color=discord.Color.from_rgb(255, 0, 50) # Rouge YouTube
        )
        embed.set_author(name="Lecture en cours 🎵", icon_url=self.user.display_avatar.url)
        
        # Gestion visuelle (Image + Barre de progression)
        if track.artwork: 
            embed.set_thumbnail(url=track.artwork)
        
        duration = format_time(track.length)
        embed.add_field(name="Artiste", value=track.author, inline=True)
        embed.add_field(name="Durée", value=duration, inline=True)
        embed.add_field(name="Demandé par", value=track.source, inline=True) # Affiche la source (Youtube/Spotify)

        # Envoi de l'interface
        view = MusicControls(player)
        await player.home.send(embed=embed, view=view)

    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        """Gère automatiquement la suite de la file d'attente"""
        player = payload.player
        if not player: return
        
        # Si la file n'est pas vide, on joue la suite
        if not player.queue.is_empty:
            next_track = player.queue.get()
            await player.play(next_track)
        else:
            # Si c'était la dernière, on ne fait rien (ou on peut déconnecter après un délai)
            pass

bot = MusicBot()

# --- COMMANDES SLASH ---

@bot.tree.command(name="play", description="Lance une musique (YouTube, Spotify, SoundCloud...)")
@app_commands.describe(recherche="Titre ou lien de la musique")
async def play(interaction: discord.Interaction, recherche: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ **Tu dois être dans un salon vocal !**", ephemeral=True)
    
    if not wavelink.Pool.get_node():
        return await interaction.response.send_message("❌ **Lavalink démarre... Réessaie dans 30 secondes.**", ephemeral=True)

    await interaction.response.defer()

    # Connexion au vocal
    if not interaction.guild.voice_client:
        try:
            vc: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
        except Exception as e:
            return await interaction.followup.send("❌ Impossible de rejoindre le salon.")
    else:
        vc: wavelink.Player = interaction.guild.voice_client

    vc.home = interaction.channel # Définit où envoyer les messages
    vc.autoplay = wavelink.AutoPlayMode.partial # Active l'autoplay intelligent si la file est vide

    # Recherche
    try:
        tracks = await wavelink.Playable.search(recherche)
    except Exception as e:
        return await interaction.followup.send(f"❌ Erreur de recherche : {e}")

    if not tracks:
        return await interaction.followup.send("❌ Aucune musique trouvée.")

    # Gestion Playlist vs Track unique
    if isinstance(tracks, wavelink.Playlist):
        added = await vc.queue.put_wait(tracks)
        embed = discord.Embed(
            title="✅ Playlist ajoutée",
            description=f"**{tracks.name}**\nAjout de `{added}` pistes à la file.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)
    else:
        track = tracks[0]
        await vc.queue.put_wait(track)
        embed = discord.Embed(
            title="✅ Ajouté à la file",
            description=f"**{track.title}**\n*{track.author}*",
            color=discord.Color.green()
        )
        if track.artwork: embed.set_thumbnail(url=track.artwork)
        await interaction.followup.send(embed=embed)
        
    # Si rien ne joue, on lance la musique
    if not vc.playing:
        await vc.play(vc.queue.get())

@bot.tree.command(name="queue", description="Affiche la file d'attente actuelle")
async def queue(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client
    if not vc or (not vc.playing and not vc.queue):
        return await interaction.response.send_message("📭 **La file d'attente est vide.**", ephemeral=True)

    queue_list = ""
    # Affiche la musique en cours
    if vc.playing:
        current = vc.current
        queue_list += f"**Lecture en cours :**\n🎶 [{current.title}]({current.uri}) - *{current.author}*\n\n**File d'attente :**\n"

    # Affiche les 10 prochaines musiques
    if vc.queue:
        for i, track in enumerate(vc.queue[:10]):
            queue_list += f"`{i+1}.` {track.title} - *{track.author}*\n"
        
        remaining = len(vc.queue) - 10
        if remaining > 0:
            queue_list += f"\n*...et {remaining} autres musiques.*"
    else:
        queue_list += "*Aucune musique après celle-ci.*"

    embed = discord.Embed(title="📜 File d'attente", description=queue_list, color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="volume", description="Change le volume du bot (0 à 100)")
@app_commands.describe(niveau="Le volume en pourcentage (défaut: 100)")
async def volume(interaction: discord.Interaction, niveau: int):
    vc: wavelink.Player = interaction.guild.voice_client
    if not vc:
        return await interaction.response.send_message("❌ Je ne suis pas connecté.", ephemeral=True)
    
    vol = max(0, min(100, niveau)) # Borne entre 0 et 100
    await vc.set_volume(vol)
    
    embed = discord.Embed(description=f"🔊 **Volume réglé sur {vol}%**", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stop", description="Arrête tout et déconnecte le bot")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("👋 **Au revoir !**")
    else:
        await interaction.response.send_message("❌ Je ne suis pas connecté.", ephemeral=True)

@bot.tree.command(name="skip", description="Passe à la musique suivante")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.playing:
        await vc.skip(force=True)
        await interaction.response.send_message("⏭️ **Musique passée.**")
    else:
        await interaction.response.send_message("❌ Rien à passer.", ephemeral=True)

@bot.tree.command(name="now", description="Affiche la musique en cours avec la barre de progression")
async def now(interaction: discord.Interaction):
    vc: wavelink.Player = interaction.guild.voice_client
    if not vc or not vc.playing:
        return await interaction.response.send_message("❌ Rien ne joue actuellement.", ephemeral=True)
    
    track = vc.current
    position = int(vc.position)
    duration = int(track.length)
    
    bar = create_progress_bar(position, duration)
    time_str = f"{format_time(position)} / {format_time(duration)}"
    
    embed = discord.Embed(
        title="🎶 Lecture en cours",
        description=f"**[{track.title}]({track.uri})**\n\n{bar}\n`{time_str}`",
        color=discord.Color.from_rgb(255, 0, 50)
    )
    if track.artwork: embed.set_thumbnail(url=track.artwork)
    embed.set_footer(text=f"Volume: {vc.volume}%")
    
    await interaction.response.send_message(embed=embed)

# Lancement
token = os.getenv('DISCORD_TOKEN')
if not token:
    print("❌ ERREUR : Variable DISCORD_TOKEN manquante")
else:
    bot.run(token)
