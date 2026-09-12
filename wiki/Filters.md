# Image Filters

AI Runner includes a set of image filters for the canvas. These are implemented in the backend `airunner_services.art` package and are applied via the canvas filter panel in the web UI.

---

## Available Filters

### Basic Filters
- **BoxBlur** — Simple blur with configurable radius
- **GaussianBlur** — Gaussian blur with configurable sigma
- **UnsharpMask** — Edge enhancement

### Color Manipulation
- **Invert** — Invert image colors
- **ColorBalance** — Adjust RGB channel balance
- **Saturation** — Adjust color intensity
- **RGBNoise** — Add random noise per channel

### Special Effects
- **Dither** — Floyd-Steinberg dithering for B&W effect
- **Film** — Box blur + noise for film simulation
- **Halftone** — Dot-based halftone effect
- **PixelArt** — Reduce colors and resolution for pixel art
- **RegistrationError** — Simulate CMYK misalignment

---

## Usage

Filters are available through the canvas image editing interface in the web UI. Select an image and choose **Filters** from the toolbar.

## Creating Custom Filters

Filters extend `BaseFilter` from the `airunner_services.art` package:

```python
from PIL import Image

class MyFilter:
    def __init__(self, **kwargs):
        self.params = kwargs

    def filter(self, image: Image.Image) -> Image.Image:
        # Implement filter logic
        return processed_image
```

Custom filters can be added to the bootstrap data in `server/src/airunner_services/bootstrap/imagefilter_bootstrap_data.py`.
