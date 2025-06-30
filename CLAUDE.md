# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Start the Flask development server
python app.py

# Initialize the database (required on first run)
python database/init_db.py
```

### Environment Setup
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Configuration
- Copy `.env.example` to `.env` and configure settings
- Key environment variables:
  - `MISTRAL_API_KEY`: Mistral AI API key (optional if `USE_MOCK_OCR=true`)
  - `USE_MOCK_OCR=true`: Enable demo mode without API key
  - `DEBUG=true`: Enable Flask debug mode
  - `MAX_FILE_SIZE_MB=50`: Maximum upload file size

## Architecture Overview

### Core Components

**Flask Application (`app.py`)**
- Main web server handling HTTP requests
- OCR processing orchestration 
- File upload and URL processing
- API endpoints for external integration
- Dual-mode operation: real Mistral API or mock demo mode

**Settings Management (`database/`)**
- SQLite-based settings storage with `settings_manager.py`
- Database initialization via `init_db.py`
- Supports user preferences, profiles, and audit history
- Categories: API, Processing, UI, Visualization, Export, Performance, Security

**Frontend Architecture**
- Modular CSS architecture in `static/css/`:
  - `base/variables.css`: Theme variables and design tokens
  - `components/`: Reusable UI components (buttons, cards, forms)
  - `layout/`: Page layouts and typography
- JavaScript in `static/js/main.js` handles dynamic interactions
- Templates in `templates/` use Jinja2 templating

### Data Flow
1. User uploads file or provides URL
2. File validation and processing in `app.py`
3. OCR processing via Mistral API or mock mode
4. Results saved as Markdown/JSON files
5. Images extracted and served via `/image/<filename>` endpoint
6. Results displayed with syntax highlighting and image previews

### Key Features
- **Dual OCR Mode**: Real Mistral API integration or demo mode with mock data
- **Multi-format Support**: PDF, images (PNG/JPG), DOCX, URLs
- **Settings System**: Comprehensive preference management with profiles
- **Theme Support**: Dark/light themes with CSS custom properties
- **Image Extraction**: Base64 encoded images embedded in results
- **Export Options**: Download results as Markdown or JSON

### File Organization
```
mistral-ocr-app/
├── app.py              # Main Flask application
├── main.py             # Alternative entry point (Chinese version)
├── database/           # Settings management system
├── static/             # Frontend assets (CSS, JS, images)
├── templates/          # Jinja2 HTML templates
├── uploads/            # Temporary file storage (auto-created)
└── settings.db         # SQLite settings database
```

## Important Implementation Notes

### OCR Processing
- The application supports both real Mistral API calls and mock demo mode
- Mock mode generates placeholder content for testing without API keys
- **FIXED v2.0.1**: Images are now correctly created and displayed in demo mode
- Images are extracted as base64 and saved as PNG files with proper file handling
- Results include page-by-page Markdown with embedded images
- Automatic fallback mechanism for image creation errors

### Settings System
- All user preferences stored in SQLite database
- Supports categorized settings with type validation
- Includes audit trail for all setting changes
- Predefined profiles: Default, Academic, Business, Performance

### Security Considerations
- File validation by extension and MIME type
- Secure filename handling with `werkzeug.utils.secure_filename`
- Temporary file cleanup after processing
- API key stored in environment variables only

### Frontend Patterns
- CSS custom properties for theming
- Modular component-based architecture
- Responsive design with mobile-first approach
- Progressive enhancement with JavaScript

## Recent Fixes (v2.0.3)

### Critical Real API Image Issue Resolution
**Problem**: Images from real Mistral OCR API not displaying (logs showed 0 images)
**Root Causes**: 
1. Mistral OCR API returns `0` images in `page.images` but embeds links in markdown
2. Frontend requests `/img-0.jpeg` instead of processed paths
3. Missing markdown parser for extracting image references

**Solution v2.0.3**: Dual-level image processing system

**Key Changes**:
- `app.py:46-69` - Added `extract_images_from_markdown()` function with regex parsing
- `app.py:185-191` - Enhanced API response logging to debug structure
- `app.py:222-284` - Implemented dual processing: base64 from API + markdown links
- `app.py:501-521` - Added `serve_markdown_image()` route for direct markdown requests
- Added regex pattern: `r'!\[([^\]]*)\]\(([^)]+\.(jpeg|jpg|png|gif|webp))\)'`
- SVG placeholder generation with contextual information
- Full compatibility with real Mistral OCR API behavior