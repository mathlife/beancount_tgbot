import os
import asyncio
import datetime
from telethon import TelegramClient
from telethon.tl.types import InputPeerSelf

# Configuration
# You can set these in env vars or input interactively
API_ID = os.getenv('TG_API_ID')
API_HASH = os.getenv('TG_API_HASH')
SESSION_NAME = 'export_session'
OUTPUT_DIR = 'data/exports'

async def get_credentials():
    global API_ID, API_HASH
    if not API_ID:
        API_ID = input("Enter API ID: ").strip()
    if not API_HASH:
        API_HASH = input("Enter API HASH: ").strip()
    return int(API_ID), API_HASH

async def get_dialog_choice(client):
    """Let user choose which dialog to export."""
    print("\nFetching dialogs...")
    dialogs = []
    async for d in client.iter_dialogs(limit=20):
        dialogs.append(d)
        
    print("\nSelect chat to export:")
    print("0. [Saved Messages] (收藏夹)")
    for i, d in enumerate(dialogs):
        name = d.name or "Deleted Account"
        print(f"{i+1}. {name} (ID: {d.id})")
        
    while True:
        try:
            choice = input("\nEnter choice (0-20): ").strip()
            if choice == '0':
                return InputPeerSelf(), "Saved Messages"
            idx = int(choice) - 1
            if 0 <= idx < len(dialogs):
                target = dialogs[idx]
                return target, target.name
        except ValueError:
            pass
        print("Invalid choice.")

async def export_history(client, entity, chat_name):
    print(f"\nStarting export for: {chat_name}")
    
    # Safe filename
    safe_name = "".join([c for c in chat_name if c.isalnum() or c in (' ', '-', '_')]).strip()
    chat_dir = os.path.join(OUTPUT_DIR, safe_name)
    media_dir = os.path.join(chat_dir, 'media')
    os.makedirs(media_dir, exist_ok=True)
    
    md_file_path = os.path.join(chat_dir, 'messages.md')
    
    total_count = 0
    
    with open(md_file_path, 'w', encoding='utf-8') as f:
        f.write(f"# Export: {chat_name}\n\n")
        
        # Iterate reverse=True (oldest to newest) or default (newest to oldest)?
        # Default is newest to oldest. We typically want newest to oldest for logs,
        # or reverse for reading history. Let's do newest to oldest (default) and append?
        # Actually standard log is top-down. Let's write as we receive.
        
        print("Reading messages...")
        async for message in client.iter_messages(entity):
            total_count += 1
            if total_count % 100 == 0:
                print(f"Processed {total_count} messages...")
            
            # Format Date
            date_str = message.date.strftime('%Y-%m-%d %H:%M:%S')
            sender = await message.get_sender()
            sender_name = "Unknown"
            if sender:
                sender_name = getattr(sender, 'first_name', '') or getattr(sender, 'title', 'User')
            
            # Header
            header = f"\n### [{date_str}] {sender_name}\n"
            content = message.message or ""
            
            # Handle Forward
            fwd_info = ""
            if message.fwd_from:
                from_name = "Hidden Sender"
                if message.fwd_from.from_name:
                    from_name = message.fwd_from.from_name
                elif message.fwd_from.from_id:
                   # Try to resolve peer if needed, skipping for speed
                   from_name = "Channel/User"
                fwd_info = f"\n> 💡 Forwarded from: {from_name}\n"
            
            # Handle Media
            media_md = ""
            if message.media:
                # Downloading heavily slows down script.
                # Option: Download small photos?
                # For now, let's skip large files or make it optional.
                # Let's download photos only.
                if hasattr(message.media, 'photo'):
                    try:
                        path = await client.download_media(message, file=media_dir)
                        rel_path = os.path.relpath(path, chat_dir)
                        media_md = f"\n![Image]({rel_path})\n"
                    except Exception as e:
                        media_md = f"\n[Error downloading media: {e}]\n"
                elif hasattr(message.media, 'document'):
                     media_md = f"\n[Document/File attached]\n"

            # Write to file
            f.write(header)
            if fwd_info:
                f.write(fwd_info)
            f.write(f"{content}\n")
            if media_md:
                f.write(media_md)
            f.write("\n---\n")

    print(f"\nDone! Exported {total_count} messages to {md_file_path}")

async def main():
    api_id, api_hash = await get_credentials()
    
    async with TelegramClient(SESSION_NAME, api_id, api_hash) as client:
        target, name = await get_dialog_choice(client)
        await export_history(client, target, name)

if __name__ == '__main__':
    # Fix for Windows loop policy
    # if os.name == 'nt':
    #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
