import os, asyncio, datetime
print(f"🎬 مصنع الملف 71 - {datetime.datetime.now()}")
script = """ياسر: جالي تليفون الساعة 2 وربع.. جثة في شقة مهجورة في طنطا.
أمينة: الجثة بقالها 6 ساعات. شايف الرقم اللي على الحيطة؟ 71 مكتوب بدم.
ياسر: نفس الرقم اللي كان في الملف اللي اتقفل من 5 سنين.
الباب خبط.. ظرف على الأرض جواه صورة لنفس الشقة قبل الجريمة بساعة."""

async def main():
    import edge_tts
    from moviepy.editor import ColorClip, AudioFileClip
    os.makedirs("storage/autopilot", exist_ok=True)
    audio_path = "storage/autopilot/ep_final.mp3"
    await edge_tts.Communicate(script, "ar-EG-ShakirNeural").save(audio_path)
    print(f"✅ صوت: {audio_path}")
    audio = AudioFileClip(audio_path)
    base = ColorClip(size=(1080,1920), color=(10,10,10), duration=audio.duration).set_audio(audio)
    base.write_videofile("storage/autopilot/EP01_FINAL.mp4", fps=24, codec="libx264", audio_codec="aac")
    print("✅ فيديو: storage/autopilot/EP01_FINAL.mp4")

import asyncio
asyncio.run(main())
