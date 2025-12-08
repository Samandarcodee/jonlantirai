# 👨‍💻 Developer Guide - Image Generation & Editing System

## 📚 Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Key Components](#key-components)
3. [Code Structure](#code-structure)
4. [Extending the System](#extending-the-system)
5. [Troubleshooting](#troubleshooting)
6. [Best Practices](#best-practices)
7. [API Reference](#api-reference)

---

## 🏗️ Architecture Overview

### **System Flow:**

```
User Input
    ↓
Telegram Bot Handler
    ↓
Message Router (handle_message / handle_photo)
    ↓
Context Manager (user_data state)
    ↓
GoogleGeminiImageGenerator
    ↓
- generate_image() OR edit_image()
    ↓
- _detect_style()
- _enhance_*_prompt()
- _optimize_image()
    ↓
Gemini API Call
    ↓
Image Processing
    ↓
Response to User
```

### **State Management:**

```python
context.user_data = {
    'waiting_for': 'text_for_image' | 'photo_for_edit' | 'edit_instruction',
    'edit_image_bytes': bytes  # Temporary image storage for editing
}
```

---

## 🔧 Key Components

### **1. GoogleGeminiImageGenerator Class**

**Location:** `bot.py` lines ~3551-3850

**Purpose:** Core image generation and editing engine

**Key Methods:**

```python
class GoogleGeminiImageGenerator:
    def __init__(self):
        """Initialize Gemini models"""
        self.generation_model  # Gemini 2.0 Flash Experimental
        self.vision_model      # Gemini 1.5 Flash
    
    def generate_image(self, prompt: str) -> dict:
        """Generate image from text
        
        Returns:
            {
                'success': bool,
                'image_bytes': bytes
            }
        """
    
    def edit_image(self, image_bytes: bytes, prompt: str) -> dict:
        """Edit existing image
        
        Returns:
            {
                'success': bool,
                'image_bytes': bytes
            }
        """
    
    def _detect_style(self, prompt: str) -> str:
        """Detect style from prompt keywords"""
    
    def _enhance_generation_prompt(self, prompt: str) -> str:
        """Enhance prompt for generation with quality controls"""
    
    def _enhance_edit_prompt(self, prompt: str) -> str:
        """Enhance prompt for editing with preservation rules"""
    
    def _optimize_image(self, image_bytes: bytes) -> bytes:
        """Optimize image size and quality"""
```

### **2. Message Handlers**

**Location:** `bot.py` lines ~3264-3455

**Key Functions:**

```python
async def handle_message(update, context):
    """Handle text messages
    
    Routes to:
    - Text-to-image generation (waiting_for='text_for_image')
    - Edit instruction input (waiting_for='edit_instruction')
    """

async def handle_photo(update, context):
    """Handle photo uploads
    
    Routes to:
    - Image editing preparation (waiting_for='photo_for_edit')
    - Image-to-video (default, not covered in this guide)
    """
```

### **3. Menu Handlers**

**Location:** `bot.py` lines ~3488-3600

**Key Functions:**

```python
async def menu_text_to_image(update, context):
    """Display text-to-image menu
    Sets: context.user_data['waiting_for'] = 'text_for_image'
    """

async def menu_edit_image(update, context):
    """Display image editing menu
    Sets: context.user_data['waiting_for'] = 'photo_for_edit'
    """

async def back_to_main_menu(update, context):
    """Return to main menu
    Clears: waiting_for, edit_image_bytes
    """
```

---

## 📂 Code Structure

### **File Organization:**

```
/workspace/
├── bot.py                              # Main bot code
│   ├── Imports & Configuration         # Lines 1-70
│   ├── UserDatabase Class              # Lines 71-200
│   ├── ... other features ...
│   ├── GoogleGeminiImageGenerator      # Lines 3551-3850
│   ├── Message Handlers                # Lines 3264-3455
│   ├── Menu Handlers                   # Lines 3488-3600
│   └── Main Application                # Lines 3742+
│
├── IMAGE_GENERATION_EDITING_SYSTEM.md  # Comprehensive docs
├── QUICK_REFERENCE_GUIDE.md            # User quick reference
├── IMPLEMENTATION_SUMMARY.md           # Implementation details
└── DEVELOPER_GUIDE.md                  # This file
```

### **State Flow Diagram:**

```
IDLE
  ↓ (User clicks "✍️ Matn → Rasm")
TEXT_FOR_IMAGE
  ↓ (User sends text)
PROCESSING → COMPLETE → IDLE

IDLE
  ↓ (User clicks "🎨 Rasmni O'zgartir")
PHOTO_FOR_EDIT
  ↓ (User sends photo)
EDIT_INSTRUCTION
  ↓ (User sends text)
PROCESSING → COMPLETE → IDLE
```

---

## 🚀 Extending the System

### **1. Adding New Styles**

**File:** `bot.py` → `GoogleGeminiImageGenerator._detect_style()`

```python
def _detect_style(self, prompt):
    """Add new style here"""
    
    style_keywords = {
        'realistic': [...],
        'cartoon': [...],
        # ADD NEW STYLE:
        'cyberpunk': ['cyberpunk', 'neon', 'dystopian', 'tech noir'],
    }
    
    # Detection logic remains the same
```

**Then add to `_enhance_generation_prompt()`:**

```python
style_enhancements = {
    'realistic': (...),
    'cartoon': (...),
    # ADD ENHANCEMENT:
    'cyberpunk': (
        "cyberpunk style, neon lights, dystopian atmosphere, "
        "futuristic tech, dark mood, high-tech low-life aesthetic"
    )
}
```

### **2. Adding New Quality Controls**

**File:** `bot.py` → `GoogleGeminiImageGenerator._enhance_generation_prompt()`

```python
enhanced = (
    f"Create a high-quality, detailed image: {prompt}\n\n"
    f"STYLE: {style_enhancement}\n\n"
    f"QUALITY REQUIREMENTS:\n"
    # ADD NEW REQUIREMENTS:
    f"- Your new requirement here\n"
    f"- Another requirement\n"
    # ... rest of requirements
)
```

### **3. Adding Image Filters/Post-Processing**

**File:** `bot.py` → Create new method in `GoogleGeminiImageGenerator`

```python
def _apply_filters(self, image_bytes, filter_type):
    """Apply post-processing filters"""
    from PIL import Image, ImageEnhance, ImageFilter
    
    img = Image.open(io.BytesIO(image_bytes))
    
    if filter_type == 'sharpen':
        img = img.filter(ImageFilter.SHARPEN)
    elif filter_type == 'enhance':
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.2)
    
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=98)
    return output.getvalue()
```

**Then call in `generate_image()` or `edit_image()`:**

```python
image_data = part.inline_data.data
# Apply filter before returning
image_data = self._apply_filters(image_data, 'sharpen')
return {'image_bytes': image_data, 'success': True}
```

### **4. Adding Usage Analytics**

**File:** `bot.py` → Add to handlers

```python
# In handle_message() after successful generation:
user_db.add_image_generation(user.id, style=detected_style)

# In UserDatabase class:
def add_image_generation(self, user_id, style='realistic'):
    """Track image generation"""
    user_id_str = str(user_id)
    if user_id_str not in self.data:
        return
    
    if 'image_stats' not in self.data[user_id_str]:
        self.data[user_id_str]['image_stats'] = {
            'total_generated': 0,
            'total_edited': 0,
            'styles_used': {}
        }
    
    self.data[user_id_str]['image_stats']['total_generated'] += 1
    
    if style not in self.data[user_id_str]['image_stats']['styles_used']:
        self.data[user_id_str]['image_stats']['styles_used'][style] = 0
    self.data[user_id_str]['image_stats']['styles_used'][style] += 1
    
    self.save_db()
```

### **5. Adding Rate Limiting for Image Generation**

**File:** `bot.py` → Similar to video cooldown

```python
# In UserDatabase class:
IMAGE_COOLDOWN_SECONDS = 300  # 5 minutes

def can_generate_image(self, user_id):
    """Check if user can generate image"""
    if user_id in ADMIN_IDS:
        return True, 0
    
    user_id_str = str(user_id)
    if user_id_str not in self.data:
        return True, 0
    
    last_gen = self.data[user_id_str].get('last_image_generation', 0)
    current_time = time.time()
    time_since_last = current_time - last_gen
    
    if time_since_last < IMAGE_COOLDOWN_SECONDS:
        return False, IMAGE_COOLDOWN_SECONDS - time_since_last
    
    return True, 0

def record_image_generation(self, user_id):
    """Record image generation time"""
    user_id_str = str(user_id)
    self.data[user_id_str]['last_image_generation'] = time.time()
    self.save_db()

# In handle_message() before generation:
can_gen, time_left = user_db.can_generate_image(user.id)
if not can_gen:
    await update.message.reply_text(f"Wait {int(time_left)}s")
    return
```

---

## 🐛 Troubleshooting

### **Common Issues:**

#### **1. Gemini API Not Returning Image**

**Symptom:** `logger.warning("Gemini didn't return image")`

**Causes:**
- API key invalid
- Prompt violates content policy
- Network timeout

**Solutions:**
```python
# Check API key
logger.info(f"API Key: {GOOGLE_GEMINI_API_KEY[:10]}...")

# Add retry logic
def generate_image(self, prompt, retries=2):
    for attempt in range(retries):
        try:
            result = self._generate_attempt(prompt)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None
```

#### **2. Image Quality Issues**

**Symptom:** Blurry or low-quality output

**Solutions:**
```python
# Increase max_size in _optimize_image()
max_size = 2048  # Instead of 1536

# Increase JPEG quality
img.save(output, format='JPEG', quality=100)

# Add quality keywords to prompt
enhanced = f"8K quality, ultra HD, maximum detail, {prompt}"
```

#### **3. Face Preservation Not Working**

**Symptom:** Faces change during editing

**Solutions:**
```python
# Make preservation rules MORE explicit
edit_instruction = (
    f"CRITICAL RULE: DO NOT CHANGE THE PERSON'S FACE IN ANY WAY. "
    f"The face must remain EXACTLY the same as the original. "
    f"ONLY change: {prompt}. "
    f"Keep face, identity, expressions UNCHANGED."
)

# Lower temperature even more
temperature=0.1  # Instead of 0.2
```

#### **4. Memory Issues with Large Images**

**Symptom:** Bot crashes or timeouts with large images

**Solutions:**
```python
def _optimize_image(self, image_bytes):
    """Add size check"""
    # Check size before processing
    if len(image_bytes) > 10 * 1024 * 1024:  # 10MB
        logger.warning("Image too large, aggressive compression")
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85)
        return output.getvalue()
    
    # Normal processing
    ...
```

---

## 📖 Best Practices

### **1. Error Handling**

```python
# Always use try-except with specific errors
try:
    result = imagen_generator.generate_image(text)
except google.api_core.exceptions.GoogleAPIError as e:
    logger.error(f"Google API error: {e}")
    await update.message.reply_text("API service temporarily unavailable")
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    await update.message.reply_text("Unexpected error occurred")
```

### **2. Logging**

```python
# Log at appropriate levels
logger.info(f"User {user.id} started image generation")  # Normal flow
logger.warning(f"No image returned for user {user.id}")  # Recoverable issue
logger.error(f"Critical error: {e}", exc_info=True)      # Serious issue

# Include user context
logger.info(f"[User {user.id}] {message}")
```

### **3. User Feedback**

```python
# Always provide:
# 1. Progress indication
wait_msg = await update.message.reply_text("Processing...")

# 2. Clear success/failure
await update.message.reply_text("✅ Success!")
# or
await update.message.reply_text("❌ Failed: [reason]")

# 3. Next steps
await update.message.reply_text(
    "✅ Done!\n\n"
    "Try another or /start for menu"
)
```

### **4. State Management**

```python
# Always clean up state
try:
    # Process
    result = process_image()
finally:
    # Clean up even if error
    context.user_data.pop('waiting_for', None)
    context.user_data.pop('edit_image_bytes', None)
```

### **5. Testing**

```python
# Create test function
async def test_image_generation():
    """Test various prompts"""
    test_prompts = [
        "realistic sunset",
        "cartoon cat",
        "very long prompt with lots of details...",
        "🙂",  # Test emoji
        "",    # Test empty
    ]
    
    for prompt in test_prompts:
        logger.info(f"Testing: {prompt}")
        result = imagen_generator.generate_image(prompt)
        assert result is not None or prompt == ""
```

---

## 📚 API Reference

### **GoogleGeminiImageGenerator**

#### **`__init__(self)`**
```python
"""Initialize image generator with Gemini models

Initializes:
    - generation_model: Gemini 2.0 Flash Experimental
    - vision_model: Gemini 1.5 Flash

Raises:
    Exception: If model initialization fails
"""
```

#### **`generate_image(self, prompt: str) -> dict`**
```python
"""Generate image from text description

Args:
    prompt (str): User's text description

Returns:
    dict: {
        'success': True if successful,
        'image_bytes': bytes of generated image
    } or None if failed

Process:
    1. Detect style from prompt
    2. Enhance prompt with quality controls
    3. Call Gemini API
    4. Extract and return image bytes
"""
```

#### **`edit_image(self, image_bytes: bytes, prompt: str) -> dict`**
```python
"""Edit existing image based on instructions

Args:
    image_bytes (bytes): Original image data
    prompt (str): Edit instructions

Returns:
    dict: {
        'success': True if successful,
        'image_bytes': bytes of edited image
    } or None if failed

Process:
    1. Optimize source image
    2. Enhance prompt with preservation rules
    3. Load image with PIL
    4. Call Gemini API with image + instruction
    5. Extract and return edited image bytes
"""
```

#### **`_detect_style(self, prompt: str) -> str`**
```python
"""Detect requested style from prompt

Args:
    prompt (str): User's text

Returns:
    str: Detected style (realistic, cartoon, etc.)
         Default: 'realistic'

Styles Detected:
    - realistic, cartoon, cinematic, minimalistic
    - artistic, sketch, 3d, vintage, modern, fantasy
"""
```

#### **`_enhance_generation_prompt(self, user_prompt: str) -> str`**
```python
"""Enhance prompt for image generation

Args:
    user_prompt (str): Original user prompt

Returns:
    str: Enhanced prompt with:
        - Style-specific enhancements
        - Quality requirements
        - Technical specifications

Adds:
    - Style keywords
    - Quality controls (4K, sharp, etc.)
    - Composition rules
    - Negative prompts (no text, etc.)
"""
```

#### **`_enhance_edit_prompt(self, user_prompt: str) -> str`**
```python
"""Enhance prompt for image editing

Args:
    user_prompt (str): Original edit instruction

Returns:
    str: Enhanced prompt with:
        - Preservation rules
        - Quality requirements
        - Edit-specific guidelines

Adds:
    - Style detection
    - Quality maintenance
    - Seamless integration requirements
"""
```

#### **`_optimize_image(self, image_bytes: bytes) -> bytes`**
```python
"""Optimize image for processing

Args:
    image_bytes (bytes): Original image data

Returns:
    bytes: Optimized image data

Optimizations:
    - Convert to RGB if needed
    - Resize to optimal range (512-1536px)
    - Maintain aspect ratio
    - High-quality JPEG encoding (98%)
    - LANCZOS resampling for quality
"""
```

---

## 🔐 Security Considerations

### **1. Input Validation**

```python
# Validate image size
if len(image_bytes) > 10 * 1024 * 1024:  # 10MB
    raise ValueError("Image too large")

# Validate prompt length
if len(prompt) > 1000:
    prompt = prompt[:1000]
```

### **2. Content Filtering**

```python
# Gemini has built-in content filtering
# But you can add additional checks:

BLOCKED_WORDS = ['explicit', 'violence', ...]

def is_safe_prompt(prompt):
    """Check if prompt is safe"""
    lower_prompt = prompt.lower()
    return not any(word in lower_prompt for word in BLOCKED_WORDS)
```

### **3. Rate Limiting**

```python
# Already implemented for video
# Add for images if needed (see section 5 in Extending)
```

### **4. User Privacy**

```python
# Don't log prompts with personal info
logger.info(f"User {user.id} generated image")  # Good
# logger.info(f"Prompt: {prompt}")  # Avoid if contains names, etc.

# Clean up temp data
context.user_data.pop('edit_image_bytes', None)  # After use
```

---

## 📊 Performance Optimization

### **1. Async Operations**

```python
# Use asyncio for parallel operations
import asyncio

async def generate_with_timeout(prompt, timeout=60):
    """Generate with timeout"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(imagen_generator.generate_image, prompt),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error("Generation timeout")
        return None
```

### **2. Caching**

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_enhanced_prompt(prompt, style):
    """Cache enhanced prompts"""
    # Enhancement logic
    return enhanced_prompt
```

### **3. Image Compression**

```python
# For temporary storage, use aggressive compression
img.save(output, format='JPEG', quality=85, optimize=True)
```

---

## 🧪 Testing Guide

### **Unit Tests:**

```python
import unittest

class TestImageGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = GoogleGeminiImageGenerator()
    
    def test_style_detection(self):
        """Test style detection"""
        self.assertEqual(
            self.generator._detect_style("realistic photo"),
            "realistic"
        )
        self.assertEqual(
            self.generator._detect_style("cartoon character"),
            "cartoon"
        )
    
    def test_prompt_enhancement(self):
        """Test prompt enhancement"""
        enhanced = self.generator._enhance_generation_prompt("cat")
        self.assertIn("4K", enhanced)
        self.assertIn("quality", enhanced.lower())
    
    def test_image_optimization(self):
        """Test image optimization"""
        # Create dummy image
        img = Image.new('RGB', (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        
        optimized = self.generator._optimize_image(buffer.getvalue())
        self.assertIsInstance(optimized, bytes)
        self.assertGreater(len(optimized), 0)
```

### **Integration Tests:**

```python
async def test_full_generation_flow():
    """Test complete generation flow"""
    # Requires valid API key
    result = imagen_generator.generate_image("realistic sunset")
    
    assert result is not None
    assert result.get('success') is True
    assert 'image_bytes' in result
    assert len(result['image_bytes']) > 0
```

---

## 📝 Maintenance Checklist

### **Weekly:**
- [ ] Check error logs for patterns
- [ ] Monitor API usage and costs
- [ ] Review user feedback
- [ ] Check performance metrics

### **Monthly:**
- [ ] Update dependencies
- [ ] Review and update documentation
- [ ] Analyze usage statistics
- [ ] Optimize prompts based on results

### **Quarterly:**
- [ ] Major feature updates
- [ ] Security audit
- [ ] Performance optimization review
- [ ] User survey for improvements

---

## 🔗 Useful Resources

- **Gemini API Docs:** https://ai.google.dev/docs
- **Telegram Bot API:** https://core.telegram.org/bots/api
- **PIL/Pillow Docs:** https://pillow.readthedocs.io/
- **Python Async:** https://docs.python.org/3/library/asyncio.html

---

## 📧 Contact & Support

**For Issues:**
- Check logs in bot console
- Review error messages
- Check this guide
- Contact admin

**For Enhancements:**
- Document proposal
- Test implementation
- Update documentation
- Submit for review

---

**Last Updated:** December 8, 2025
**Version:** 2.0
**Maintained By:** Development Team
