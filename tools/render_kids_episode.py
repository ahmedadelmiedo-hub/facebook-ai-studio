"""Build a private, review-only MP4 for a Hikayatuna Kids episode.

Uses Edge TTS Arabic Egyptian male voice, original Pillow-drawn artwork, FFmpeg,
and the repository's scene renderer. No public upload or third-party music.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import edge_tts
from PIL import Image, ImageDraw

from core.captions import CaptionCue, build_estimated_cues, write_arabic_ass
from core.scene_renderer import probe_duration, render_visual_video
VOICE = "ar-EG-ShakirNeural"
W, H = 1920, 1080


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-3000:])


def draw_character(draw: ImageDraw.ImageDraw, kind: str, x: int, y: int, scale: float = 1.0) -> None:
    def e(box, fill, outline="#26334A", width=7):
        draw.ellipse(tuple(int(v) for v in box), fill=fill, outline=outline, width=width)
    if kind == "nouri":
        # Mint-green firefly with lantern belly and tiny wings.
        e((x-82*scale, y-86*scale, x+82*scale, y+78*scale), "#8CE6B5")
        e((x-58*scale, y-132*scale, x-2*scale, y-66*scale), "#D9F7FF")
        e((x+5*scale, y-132*scale, x+61*scale, y-66*scale), "#D9F7FF")
        e((x-46*scale, y-22*scale, x+46*scale, y+66*scale), "#FFD96B", outline="#D49A2A", width=5)
        e((x-38*scale, y-35*scale, x-20*scale, y-17*scale), "#26334A", outline="#26334A", width=2)
        e((x+20*scale, y-35*scale, x+38*scale, y-17*scale), "#26334A", outline="#26334A", width=2)
        draw.arc((x-34*scale,y-8*scale,x+34*scale,y+30*scale), 10, 170, fill="#26334A", width=5)
        draw.line((x-32*scale,y-78*scale,x-58*scale,y-116*scale), fill="#26334A", width=6)
        draw.line((x+32*scale,y-78*scale,x+58*scale,y-116*scale), fill="#26334A", width=6)
        e((x-67*scale,y-128*scale,x-52*scale,y-113*scale), "#FFD96B", outline="#D49A2A", width=2)
        e((x+52*scale,y-128*scale,x+67*scale,y-113*scale), "#FFD96B", outline="#D49A2A", width=2)
    elif kind == "rima":
        # Child explorer: turquoise headband, coral clothes, star badge.
        e((x-72*scale,y-104*scale,x+72*scale,y+42*scale), "#F4C7A1")
        draw.pieslice((x-80*scale,y-125*scale,x+80*scale,y+55*scale),180,360,fill="#49352F",outline="#26334A",width=6)
        draw.arc((x-74*scale,y-114*scale,x+74*scale,y-18*scale),190,350,fill="#35C8C0",width=max(8,int(15*scale)))
        e((x-42*scale,y-38*scale,x-22*scale,y-18*scale), "#26334A", outline="#26334A", width=2)
        e((x+22*scale,y-38*scale,x+42*scale,y-18*scale), "#26334A", outline="#26334A", width=2)
        draw.arc((x-30*scale,y-5*scale,x+30*scale,y+26*scale),10,170,fill="#9C4F4B",width=5)
        draw.rounded_rectangle((x-100*scale,y+35*scale,x+100*scale,y+220*scale),radius=int(48*scale),fill="#F28D83",outline="#26334A",width=7)
        e((x+35*scale,y+76*scale,x+76*scale,y+117*scale), "#FFD96B", outline="#D49A2A", width=3)
    elif kind == "timo":
        # Small orange fox with yellow hoodie and green bag.
        e((x-78*scale,y-88*scale,x+78*scale,y+80*scale), "#F39A4A")
        draw.polygon([(x-70*scale,y-55*scale),(x-88*scale,y-155*scale),(x-12*scale,y-100*scale)],fill="#F39A4A",outline="#26334A")
        draw.polygon([(x+70*scale,y-55*scale),(x+88*scale,y-155*scale),(x+12*scale,y-100*scale)],fill="#F39A4A",outline="#26334A")
        e((x-47*scale,y-24*scale,x-27*scale,y-4*scale), "#26334A", outline="#26334A", width=2)
        e((x+27*scale,y-24*scale,x+47*scale,y-4*scale), "#26334A", outline="#26334A", width=2)
        e((x-27*scale,y+20*scale,x+27*scale,y+58*scale), "#FFF0D8", outline="#D98B55", width=3)
        e((x-9*scale,y+28*scale,x+9*scale,y+44*scale), "#26334A", outline="#26334A", width=2)
        draw.rounded_rectangle((x-92*scale,y+70*scale,x+92*scale,y+220*scale),radius=int(42*scale),fill="#FFD35E",outline="#26334A",width=7)
        draw.rounded_rectangle((x+55*scale,y+95*scale,x+115*scale,y+185*scale),radius=int(20*scale),fill="#65B98A",outline="#26334A",width=5)


def make_scene_art(index: int, out: Path) -> None:
    palettes = [
        ("#15294E", "#4D6A91"), ("#203B61", "#7896B7"),
        ("#25486A", "#89B7B4"), ("#1D3C61", "#789CB8"),
        ("#24395C", "#6F789E"), ("#142544", "#465A86"),
    ]
    top, bottom = palettes[index-1]
    image = Image.new("RGB", (W, H), top)
    px = image.load()
    import PIL.ImageColor as ImageColor
    a, b = ImageColor.getrgb(top), ImageColor.getrgb(bottom)
    for yy in range(H):
        t = yy / (H-1)
        color = tuple(int(a[c]*(1-t)+b[c]*t) for c in range(3))
        for xx in range(W):
            px[xx, yy] = color
    d = ImageDraw.Draw(image)
    # Stars and moon are original vector-like shapes.
    for sx, sy, r in [(160,140,10),(360,230,7),(1550,170,9),(1740,330,6),(1320,90,5),(650,120,6)]:
        d.ellipse((sx-r,sy-r,sx+r,sy+r),fill="#FFF0B2")
    d.ellipse((1450,95,1580,225),fill="#F7E6B5")
    d.ellipse((1488,72,1600,190),fill=top)
    # Bedroom window and curtain.
    d.rounded_rectangle((90,110,560,500),radius=30,fill="#263C62",outline="#D5E8F6",width=14)
    d.rectangle((315,120,330,490),fill="#D5E8F6")
    d.rectangle((105,292,545,307),fill="#D5E8F6")
    d.polygon([(75,100),(190,100),(230,510),(80,510)],fill="#6E8BB1")
    d.polygon([(460,100),(575,100),(550,510),(430,510)],fill="#6E8BB1")
    # Bed, rug, toy box.
    d.rounded_rectangle((720,660,1770,970),radius=65,fill="#D9E7F2",outline="#24344F",width=12)
    d.rounded_rectangle((760,620,1080,790),radius=50,fill="#FFF0D8",outline="#24344F",width=8)
    d.rounded_rectangle((980,835,1550,1030),radius=80,fill="#E8B5B5")
    d.rounded_rectangle((150,790,590,990),radius=35,fill="#B77F61",outline="#26334A",width=10)
    d.rectangle((170,760,570,825),fill="#DCA77B",outline="#26334A",width=8)
    # Scene-specific objects.
    if index == 3:
        for xx, yy, color in [(250,690,"#E5B84F"),(390,690,"#68B8A6"),(520,690,"#D67D7D")]:
            d.rounded_rectangle((xx,yy,xx+100,yy+100),radius=15,fill=color,outline="#26334A",width=5)
    if index == 4:
        d.ellipse((1130,120,1250,240),fill="#FFE7A5")
        for k in range(3):
            d.arc((1110+k*70,400,1330+k*70,590),190,350,fill="#D7F2F0",width=9)
    if index == 5:
        d.polygon([(1260,420),(1290,485),(1360,495),(1310,540),(1325,610),(1260,575),(1195,610),(1210,540),(1160,495),(1230,485)],fill="#FFD96B")
    # Nouri is present in every scene; friends join progressively.
    draw_character(d,"nouri",930,500,0.95)
    if index >= 2:
        draw_character(d,"rima",570,555,0.78)
    if index >= 3:
        draw_character(d,"timo",1510,560,0.72)
    # Soft floor line.
    d.line((0,1010,W,1010),fill="#D4E3EF",width=8)
    out.parent.mkdir(parents=True,exist_ok=True)
    image.save(out,format="PNG",optimize=True)


async def make_voice(text: str, out: Path) -> None:
    communicate = edge_tts.Communicate(text, VOICE, rate="+0%", volume="+0%")
    await communicate.save(str(out))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode-id", default="kids-ep-001")
    args = parser.parse_args()
    episode_dir = ROOT / "content/production/kids" / args.episode_id
    script_path = episode_dir / "script.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    scenes = script["scenes"]
    assets = episode_dir / "assets"
    audio_dir = assets / "audio"
    image_dir = assets / "scenes"
    audio_dir.mkdir(parents=True,exist_ok=True)
    image_dir.mkdir(parents=True,exist_ok=True)

    scene_audio: list[Path] = []
    scene_durations: list[float] = []
    captions: list[CaptionCue] = []
    cursor = 0.0
    concat_list = assets / "audio.concat.txt"
    concat_entries: list[str] = []
    storyboard_scenes = []

    for idx, scene in enumerate(scenes, start=1):
        parts = [scene["narration"], scene["dialogue"]]
        if idx == len(scenes):
            parts.extend([script.get("original_song", ""), script.get("quiz", "")])
        spoken = " ".join(part.strip() for part in parts if part and part.strip())
        audio_path = audio_dir / f"scene-{idx:02d}.mp3"
        asyncio.run(make_voice(spoken,audio_path))
        duration = probe_duration(audio_path)
        image_path = image_dir / f"scene-{idx:02d}.png"
        make_scene_art(idx,image_path)
        scene_audio.append(audio_path)
        scene_durations.append(duration)
        concat_entries.append(f"file '{audio_path.resolve().as_posix()}'")
        start = cursor
        end = cursor + duration
        for cue in build_estimated_cues(spoken,duration,max_chars=48):
            captions.append(CaptionCue(start+cue.start,start+cue.end,cue.text))
        storyboard_scenes.append({
            "number":idx,"start":round(start,3),"end":round(end,3),
            "image":str(image_path.relative_to(ROOT)),
            "setting":scene["setting"],"action":scene["action"],
            "motion":{"type":"slow_zoom" if idx % 2 else "pan_left"}
        })
        cursor = end
        if idx != len(scenes):
            silence = audio_dir / f"pause-{idx:02d}.mp3"
            run(["ffmpeg","-y","-hide_banner","-loglevel","error","-f","lavfi","-i","anullsrc=r=24000:cl=mono","-t","0.65","-q:a","9",str(silence)])
            concat_entries.append(f"file '{silence.resolve().as_posix()}'")
            cursor += probe_duration(silence)

    concat_list.write_text("\n".join(concat_entries)+"\n",encoding="utf-8")
    narration = assets / "narration.mp3"
    run(["ffmpeg","-y","-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",str(concat_list),"-c:a","libmp3lame","-b:a","192k",str(narration)])
    actual_duration = probe_duration(narration)
    target_duration = 180.0
    if actual_duration > target_duration:
        raise RuntimeError(f"Arabic narration is {actual_duration:.1f}s; over the 180s target. Shorten the script before rendering.")
    # Pad with quiet room tone to a precise three-minute master; never cut spoken words.
    mastered = assets / "narration-180s.mp3"
    run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",str(narration),"-af","apad=pad_dur=180","-t","180","-c:a","libmp3lame","-b:a","192k",str(mastered)])
    # Extend the final visual scene over the closing room tone.
    storyboard_scenes[-1]["end"] = 180.0
    storyboard = {"status":"rendered_assets_ready","voice":VOICE,"duration_seconds":180,"scenes":storyboard_scenes}
    storyboard_path = episode_dir / "storyboard.json"
    storyboard_path.write_text(json.dumps(storyboard,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    captions_path = episode_dir / "captions.ass"
    write_arabic_ass(captions,captions_path,vertical=False)
    scene_plan = assets / "scene-plan.json"
    # Renderer paths are absolute to make FFmpeg independent of its working directory.
    render_plan = {"scenes":[{**s,"image":str(ROOT/s["image"])} for s in storyboard_scenes]}
    scene_plan.write_text(json.dumps(render_plan,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    output = episode_dir / "episode.mp4"
    render_visual_video(scene_plan=scene_plan,audio_path=mastered,captions_path=captions_path,output_path=output,profile="long",fps=24,fonts_dir=Path("/usr/share/fonts/truetype/noto"))
    final_duration = probe_duration(output)
    if abs(final_duration-180.0)>1.0:
        raise RuntimeError(f"Rendered MP4 duration {final_duration:.2f}s is not three minutes.")
    manifest_path = episode_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"]="rendered_for_private_review"
    manifest["provider_status"]={"text":script.get("provider","unknown"),"image":"original_local_artwork","voice":VOICE,"video":"ffmpeg"}
    manifest["quality_gate"]["status"]="blocked"
    manifest["quality_gate"]["human_approval"]=False
    manifest["quality_gate"]["media_validation"]={"mp4_exists":True,"duration_seconds":round(final_duration,2),"has_narration":True,"captions":"burned_in"}
    manifest["publishing"]={"enabled":False,"privacy":"private","youtube_video_id":None}
    manifest["artifacts"]["video"]=str(output.relative_to(ROOT))
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report={"episode_id":args.episode_id,"video":str(output.relative_to(ROOT)),"duration_seconds":round(final_duration,2),"voice":VOICE,"voice_source":"Edge TTS service; no API key configured","captions":"Arabic ASS burned into video","artwork":"original Pillow illustrations","music":"none; no unlicensed music used","privacy":"private review only","public_publish":False}
    (episode_dir/"quality-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
