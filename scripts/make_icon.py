"""Build the project's own geometric icon; Pillow is only used for this dev tool."""
from pathlib import Path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent.parent
image=Image.new('RGBA',(256,256),(0,0,0,0));draw=ImageDraw.Draw(image)
draw.rounded_rectangle((6,6,250,250),radius=52,fill='#247D6E')
draw.rounded_rectangle((48,77,208,204),radius=12,fill='#FAFDFC')
for x in (80,112,144,176):draw.line((x,83,x,202),fill='#A3C8BC',width=3)
for x in (69,101,165):draw.rounded_rectangle((x,77,x+22,146),radius=4,fill='#214D48')
draw.line((72,51,181,51),fill='#A6DBBF',width=7)
draw.ellipse((177,40,196,59),fill='#F5C988')
(root/'assets').mkdir(exist_ok=True)
image.save(root/'assets'/'lingfeng.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
