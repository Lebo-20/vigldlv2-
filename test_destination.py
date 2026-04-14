import asyncio
from uploader import uploader
from config import AUTO_CHANNEL, TOPIC_ID

async def test_dest():
    print(f"Connecting to Telegram for target: {AUTO_CHANNEL} (Topic: {TOPIC_ID})...")
    await uploader.start()
    
    test_msg = "🚀 **Vigloo Bot Destination Test**\n\nJika pesan ini muncul di topik yang benar, berarti konfigurasi sudah BERHASIL! ✅"
    
    try:
        await uploader.client.send_message(AUTO_CHANNEL, test_msg, reply_to=TOPIC_ID)
        print("✅ Message sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send message: {e}")

if __name__ == "__main__":
    asyncio.run(test_dest())
