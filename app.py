from flask import Flask, request, render_template, jsonify
from PIL import Image
import requests
import io

app = Flask(__name__)

# Your ESP32 IP address
ESP32_IP = "192.168.86.127"

# Corrected 6-color palette
PALETTE = {
    'black': (0, 0, 0, 0x0),
    'white': (255, 255, 255, 0x1),
    'yellow': (255, 255, 0, 0x2),
    'red': (200, 80, 50, 0x3),
    'blue': (100, 120, 180, 0x5),
    'green': (200, 200, 80, 0x6)
}

def rgb_to_palette_code(r, g, b):
    """Find closest color in palette"""
    min_distance = float('inf')
    closest_code = 0x1
    
    for color_name, (pr, pg, pb, code) in PALETTE.items():
        distance = (r - pr)**2 + (g - pg)**2 + (b - pb)**2
        if distance < min_distance:
            min_distance = distance
            closest_code = code
    
    return closest_code

def convert_image_to_binary(image_path, use_dithering=True):
    """Convert image to 800x480 binary format with crop-to-fill"""
    img = Image.open(image_path)
    
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Auto-rotate portrait to landscape
    if img.height > img.width:
        img = img.rotate(90, expand=True)
        print(f"Rotated portrait image to landscape")
    
    # Downscale very large images first
    if img.width > 2400 or img.height > 1440:
        img.thumbnail((2400, 1440), Image.Resampling.LANCZOS)
        print(f"Pre-scaled large image to {img.width}x{img.height}")
    
    # Calculate crop-to-fill dimensions
    img_ratio = img.width / img.height
    display_ratio = 800 / 480
    
    if img_ratio > display_ratio:
        new_height = 480
        new_width = int(480 * img_ratio)
    else:
        new_width = 800
        new_height = int(800 / img_ratio)
    
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - 800) // 2
    top = (new_height - 480) // 2
    img = img.crop((left, top, left + 800, top + 480))
    
    if use_dithering:
        palette_data = [
            0, 0, 0,
            255, 255, 255,
            255, 255, 0,
            200, 80, 50,
            100, 120, 180,
            200, 200, 80
        ]
        
        palette_img = Image.new('P', (1, 1))
        palette_img.putpalette(palette_data + [0] * (256 * 3 - len(palette_data)))
        
        img = img.quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)
        img = img.convert('RGB')
    
    binary_data = bytearray(192000)
    
    for row in range(480):
        for col in range(0, 800, 2):
            r1, g1, b1 = img.getpixel((col, row))
            r2, g2, b2 = img.getpixel((col + 1, row))
            
            code1 = rgb_to_palette_code(r1, g1, b1)
            code2 = rgb_to_palette_code(r2, g2, b2)
            
            byte_index = row * 400 + col // 2
            binary_data[byte_index] = (code1 << 4) | code2
    
    return bytes(binary_data)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'image' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['image']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        binary_data = convert_image_to_binary(file)
        
        response = requests.post(
            f'http://{ESP32_IP}/display',
            files={'file': ('image.bin', binary_data)},
            headers={'Connection': 'keep-alive'},
            timeout=120
        )
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Image displayed!'})
        else:
            return jsonify({'error': f'ESP32 error: {response.status_code}'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
