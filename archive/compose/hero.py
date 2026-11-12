"""Compose a split-screen frame: the performer's video frame on the left, her simulated twin in the tunnel on the right, with the read-out.
Usage: hero.py <video.mp4> <t_seconds> <render.png> <out.jpg> <CdA> <chip: sure|unsure|solver|learned> [title] [sub]"""
import sys, subprocess, io
from PIL import Image, ImageDraw, ImageFont, ImageFilter

video, t, render, out, cda, chip = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4], float(sys.argv[5]), sys.argv[6]
title = sys.argv[7] if len(sys.argv) > 7 else ''
sub = sys.argv[8] if len(sys.argv) > 8 else ''
HN = '/System/Library/Fonts/HelveticaNeue.ttc'
def font(size, idx=0):
    return ImageFont.truetype(HN, size, index=idx)
LIGHT, REG, MED = 7, 0, 10          # HelveticaNeue.ttc indices: 0 regular, 7 light, 10 medium
CREAM, INK, OLIVE, AMBER, RED = (239, 234, 224), (38, 40, 30), (107, 122, 42), (232, 162, 26), (210, 64, 30)

W, H = 1920, 1080
canvas = Image.new('RGB', (W, H), CREAM)
raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', video, '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True).stdout
fr = Image.open(io.BytesIO(raw)).convert('RGB')
ph = H - 120
pw = int(ph * 9 / 16)
fr = fr.resize((int(fr.width * ph / fr.height), ph), Image.LANCZOS)
fr = fr.crop(((fr.width - pw) // 2, 0, (fr.width - pw) // 2 + pw, ph))
mask = Image.new('L', (pw, ph), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw, ph), 28, fill=255)
canvas.paste(fr, (60, 60), mask)
rd = Image.open(render).convert('RGB')
rw = W - pw - 60 - 60 - 40
rh = ph
sc = max(rw / rd.width, rh / rd.height)
rd = rd.resize((int(rd.width * sc + 0.5), int(rd.height * sc + 0.5)), Image.LANCZOS)
rd = rd.crop(((rd.width - rw) // 2, (rd.height - rh) // 2, (rd.width - rw) // 2 + rw, (rd.height - rh) // 2 + rh))
m2 = Image.new('L', (rw, rh), 0); ImageDraw.Draw(m2).rounded_rectangle((0, 0, rw, rh), 28, fill=255)
x0 = 60 + pw + 40
canvas.paste(rd, (x0, 60), m2)
# soft cream panels behind the text so it stays readable over the flow lines
ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(ov)
RX = x0 + rw - 640
od.rounded_rectangle((RX, 78, x0 + rw - 22, 372), 26, fill=CREAM + (222,))
if title:
    od.rounded_rectangle((x0 + 22, H - 60 - 138, x0 + rw - 22, H - 60 - 14), 26, fill=CREAM + (222,))
canvas = Image.alpha_composite(canvas.convert('RGBA'), ov).convert('RGB')
d = ImageDraw.Draw(canvas)
# read-out: the big number is the push of a 100 km/h wind in kilograms (0.5 x 1.2 kg/m3 x (27.78 m/s)^2 x drag area / 9.81)
kg = 0.5 * 1.2 * 27.78 ** 2 * cda / 9.81
d.text((RX + 22, 92), 'WIND PUSH AT 100 KM/H', font=font(24, MED), fill=INK)
num = f'{kg:.0f}'
d.text((RX + 18, 114), num, font=font(150, LIGHT), fill=INK)
wnum = d.textlength(num, font=font(150, LIGHT))
d.text((RX + 32 + wnum, 204), 'kg', font=font(46, LIGHT), fill=INK)
d.text((RX + 48 + wnum + d.textlength('kg', font=font(46, LIGHT)), 222), f'drag area {cda:.2f} m²', font=font(24, REG), fill=(90, 92, 80))
# colours checked for red-green colour blindness (olive vs orange passes; olive vs red does not), and every state also has words
ORANGE = (224, 138, 30)
chips = dict(sure=('answered by the model · sure', OLIVE), unsure=("not sure · asking the real solver", ORANGE),
             solver=('answered by the real solver', INK), learned=('learned · answered by the model', OLIVE))
if len(sys.argv) > 9:
    chips[chip] = (sys.argv[9], chips[chip][1])
txt, col = chips[chip]
f = font(30, MED)
tw = d.textlength(txt, font=f)
cx, cy = RX + 22, 300
d.rounded_rectangle((cx, cy, cx + tw + 62, cy + 54), 27, fill=col)
d.ellipse((cx + 18, cy + 19, cx + 34, cy + 35), fill=CREAM)
d.text((cx + 46, cy + 9), txt, font=f, fill=CREAM)
if title:
    d.text((x0 + 44, H - 60 - 118), title, font=font(52, LIGHT), fill=INK)
if sub:
    d.text((x0 + 46, H - 60 - 52), sub, font=font(26, REG), fill=(90, 92, 80))
d.text((60 + 24, 60 + ph - 50), 'recorded clip · tracked with MediaPipe Pose', font=font(22, REG), fill=(255, 255, 255))
canvas.save(out, quality=90)
print(out)
