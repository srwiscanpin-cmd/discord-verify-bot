import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from flask import Flask, request, jsonify
import threading
import asyncio

# ===== CONFIG =====
BOT_TOKEN = os.environ.get("MTUwMzY3MDQzNjk3Njc4NzU2Nw.GHhP6e.YSYGY-QB3pxs05387B2XbLVSYLB8e57loq9Hjc")
VERIFY_CHANNEL_ID = int(os.environ.get("1512850528080494894"))
LOG_CHANNEL_ID = int(os.environ.get("1512853167036170435"))
MAP_LINK = os.environ.get("https://www.roblox.com/games/82655739311380/unnamed")
API_SECRET = os.environ.get("kimminja")
API_PORT = int(os.environ.get("PORT", 5000))

# ===== RANK CONFIG =====
# format: "ยศในกลุ่ม Roblox" : ("OR Code", "ชื่อยศ Discord")
RANK_MAP = {
    "Private":           ("OR-1", "PVT"),
    "Private First Class": ("OR-2", "PFC"),
    "Lance Corporal":    ("OR-3", "LCPL"),
    "Corporal":          ("OR-4", "CPL"),
    "Sergeant":          ("OR-5", "SGT"),
    "Staff Master 3":    ("OR-6", "SM3"),
    "Staff Master 2":    ("OR-7", "SM2"),
    "Staff Master 1":    ("OR-8", "SM1"),
    "NCO":               ("OR-D", "NCO"),
    # เพิ่มยศได้เองด้านล่าง
    # "ชื่อยศในRoblox": ("OR-X", "ชื่อย่อ"),
}

# ===== INTENTS =====
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# เก็บ pending verifications: {discord_user_id: roblox_username}
pending_verifications = {}

# ===== FLASK API (รับข้อมูลจาก Roblox) =====
app = Flask(__name__)

@app.route("/verify", methods=["POST"])
def roblox_verify():
    """Endpoint รับข้อมูลจากแมพ Roblox"""
    data = request.json
    secret = data.get("secret")
    
    if secret != API_SECRET:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    discord_id = int(data.get("discord_id"))
    roblox_name = data.get("roblox_name")
    roblox_rank = data.get("rank")  # ยศในกลุ่ม Roblox
    group_id_match = data.get("rank_id")
    
    # ส่ง event ไปให้ Discord bot
    asyncio.run_coroutine_threadsafe(
        handle_roblox_verification(discord_id, roblox_name, roblox_rank),
        bot.loop
    )
    
    return jsonify({"success": True})


async def handle_roblox_verification(discord_id: int, roblox_name: str, roblox_rank: str):
    """จัดการเปลี่ยนชื่อและยืนยัน"""
    guild = bot.guilds[0]  # เอา guild แรก (ถ้ามีหลาย server ให้ระบุ guild ID)
    member = guild.get_member(discord_id)
    
    if not member:
        return
    
    log_ch = guild.get_channel(LOG_CHANNEL_ID)
    
    # หาข้อมูลยศ
    rank_info = RANK_MAP.get(roblox_rank)
    
    if not rank_info:
        # ยศไม่ตรง
        if log_ch:
            embed = discord.Embed(
                title="❌ ยืนยันตัวตนล้มเหลว",
                description=f"**{member.mention}** (`{roblox_name}`) ยศ `{roblox_rank}` ไม่พบในระบบ",
                color=discord.Color.red()
            )
            await log_ch.send(embed=embed)
        
        try:
            await member.send(
                f"❌ ยืนยันตัวตนล้มเหลว\n"
                f"ยศ `{roblox_rank}` ของคุณไม่พบในระบบ\n"
                f"กรุณาติดต่อผู้ดูแล"
            )
        except:
            pass
        return
    
    or_code, rank_abbr = rank_info
    new_nick = f"{or_code} {rank_abbr}, | {roblox_name}"
    
    # เปลี่ยนชื่อ
    try:
        await member.edit(nick=new_nick)
        
        # หา/สร้าง role ยศ (optional - ถ้าต้องการ)
        rank_role = discord.utils.get(guild.roles, name=rank_abbr)
        if rank_role:
            # ลบ rank roles เก่า
            old_ranks = [r for r in member.roles if r.name in [v[1] for v in RANK_MAP.values()]]
            if old_ranks:
                await member.remove_roles(*old_ranks)
            await member.add_roles(rank_role)
        
        # แจ้งผล
        if log_ch:
            embed = discord.Embed(
                title="✅ ยืนยันตัวตนสำเร็จ",
                color=discord.Color.green()
            )
            embed.add_field(name="Discord", value=member.mention, inline=True)
            embed.add_field(name="Roblox", value=roblox_name, inline=True)
            embed.add_field(name="ยศ", value=f"{or_code} {rank_abbr}", inline=True)
            embed.add_field(name="ชื่อใหม่", value=f"`{new_nick}`", inline=False)
            await log_ch.send(embed=embed)
        
        try:
            await member.send(
                f"✅ ยืนยันตัวตนสำเร็จ!\n"
                f"ชื่อของคุณถูกเปลี่ยนเป็น: `{new_nick}`"
            )
        except:
            pass
            
    except discord.Forbidden:
        if log_ch:
            await log_ch.send(f"⚠️ ไม่สามารถเปลี่ยนชื่อ {member.mention} ได้ (ไม่มีสิทธิ์)")


# ===== DISCORD UI =====

class VerifyModal(discord.ui.Modal, title="ยืนยันตัวตน"):
    roblox_name = discord.ui.TextInput(
        label="ชื่อ Roblox ของคุณ",
        placeholder="กรอกชื่อ Roblox ที่ใช้ในกลุ่ม...",
        required=True,
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        name = self.roblox_name.value.strip()
        user_id = interaction.user.id
        
        # เก็บชื่อ pending
        pending_verifications[user_id] = name
        
        # สร้าง link พร้อม user_id เพื่อให้แมพรู้ว่าใคร
        verify_link = f"{MAP_LINK}?uid={user_id}"
        
        embed = discord.Embed(
            title="🎮 ยืนยันตัวตนใน Roblox",
            description=(
                f"คุณ: **{name}**\n\n"
                f"กรุณายืนยันตัวตนในแมพของเรา:\n"
                f"👉 [คลิกเพื่อเข้าแมพ]({verify_link})\n\n"
                f"ขั้นตอน:\n"
                f"1. กดลิ้งเข้าแมพด้านบน\n"
                f"2. เข้าเกม Roblox\n"
                f"3. ระบบจะตรวจสอบยศของคุณอัตโนมัติ\n"
                f"4. ชื่อ Discord จะถูกเปลี่ยนตามยศ"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Discord ID: {user_id}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="✅ ยืนยันตัวตน",
        style=discord.ButtonStyle.success,
        custom_id="verify_btn"
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        # เช็คว่ายืนยันแล้วหรือยัง
        if interaction.user.id in pending_verifications:
            await interaction.response.send_message(
                f"⏳ คุณได้ยื่นคำขอยืนยันแล้ว (`{pending_verifications[interaction.user.id]}`)\n"
                f"กรุณาเข้าแมพเพื่อยืนยัน",
                ephemeral=True
            )
            return
        
        await interaction.response.send_modal(VerifyModal())


# ===== COMMANDS =====

@tree.command(name="setup_verify", description="ตั้งค่าส่งปุ่มยืนยันตัวตน (Admin เท่านั้น)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔐 ยืนยันตัวตน",
        description=(
            "กดปุ่มด้านล่างเพื่อยืนยันตัวตนเข้าสู่กลุ่ม\n\n"
            "**ขั้นตอน:**\n"
            "1️⃣ กดปุ่ม **ยืนยันตัวตน**\n"
            "2️⃣ ใส่ชื่อ Roblox ของคุณ\n"
            "3️⃣ เข้าแมพเพื่อยืนยันยศ\n"
            "4️⃣ ชื่อ Discord จะถูกเปลี่ยนอัตโนมัติ"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text="ระบบยืนยันตัวตนอัตโนมัติ")
    
    await interaction.response.send_message(embed=embed, view=VerifyButton())


@tree.command(name="check_pending", description="ดู pending verifications (Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def check_pending(interaction: discord.Interaction):
    if not pending_verifications:
        await interaction.response.send_message("ไม่มี pending verifications", ephemeral=True)
        return
    
    lines = [f"<@{uid}>: `{name}`" for uid, name in pending_verifications.items()]
    await interaction.response.send_message(
        f"**Pending ({len(lines)}):**\n" + "\n".join(lines),
        ephemeral=True
    )


@tree.command(name="clear_pending", description="ล้าง pending ของ user (Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def clear_pending(interaction: discord.Interaction, user: discord.Member):
    if user.id in pending_verifications:
        del pending_verifications[user.id]
        await interaction.response.send_message(f"ล้าง pending ของ {user.mention} แล้ว", ephemeral=True)
    else:
        await interaction.response.send_message(f"{user.mention} ไม่มี pending", ephemeral=True)


# ===== BOT EVENTS =====

@bot.event
async def on_ready():
    print(f"✅ Bot พร้อมใช้งาน: {bot.user}")
    await tree.sync()
    print("✅ Synced slash commands")
    
    # เพิ่ม persistent view
    bot.add_view(VerifyButton())


# ===== RUN FLASK + BOT =====

def run_flask():
    app.run(host="0.0.0.0", port=API_PORT, debug=False)

if __name__ == "__main__":
    # รัน Flask ใน thread แยก
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"✅ Flask API รันที่ port {API_PORT}")
    
    bot.run(BOT_TOKEN)
