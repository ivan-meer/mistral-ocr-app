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

## Recent Fixes (v2.0.8)

### Major Enhancement - PDF Comparison Mode with Fallback Image Extraction
**Issue**: Need to see actual graphics and charts when Mistral API doesn't provide base64 data
**Solution**: Comprehensive PDF comparison system with multiple image extraction methods

**Key Changes**:
- `requirements.txt` - Added PyMuPDF==1.23.26 and Pillow==10.2.0 for PDF processing
- `app.py:99-178` - New functions: `extract_pdf_pages_as_images()` and `extract_images_from_pdf()`
- `app.py:452-481` - Enhanced `mistral_ocr_processing()` with fallback image extraction
- `templates/compare.html` - New side-by-side comparison interface
- `app.py:874-893` - New routes: `/compare` and `/pdf_page/<filename>`
- `templates/index.html:44-46,501-516` - Integration with comparison mode and result storage

**Features**:
- **PDF Page Conversion**: Full pages rendered as PNG images for accurate visual comparison
- **Direct Image Extraction**: Embedded images extracted directly from PDF using PyMuPDF
- **Dual Extraction Pipeline**: Mistral API results + PDF fallback images
- **Interactive Comparison**: Side-by-side view with independent zoom controls
- **Real-time Statistics**: Image count, extraction success rates, document analysis

### Previous Fix (v2.0.7) - Critical Image Display Fix
**Issue**: Images with empty base64 data not displaying despite API detection  
**Root Cause**: Backend saved image metadata with `path: None`, causing frontend to show generic "image unavailable" message
**Solution**: Always create SVG placeholder files for images without base64 data

**Key Changes**:
- `app.py:71-94` - New `create_svg_placeholder()` function for generating informative SVG files
- `app.py:271-301` - Updated `mistral_ocr_processing()` to create placeholder files instead of null paths
- Enhanced placeholder with grid pattern, coordinates, and metadata
- Frontend now always receives a valid file path (real image or SVG placeholder)
- Consistent user experience regardless of API base64 data availability

### Previous Fix (v2.0.6) - Markdown Image Link Processing
**Issue**: Images detected by API but not properly linked in markdown output
**Solution**: Proper markdown link replacement according to Mistral OCR documentation

**Key Changes**:
- `app.py:297-327` - Correct markdown link processing with ID matching
- Enhanced image linking between API data and markdown references
- Automatic URL replacement for images with saved files
- Fallback to placeholder routes for images without base64 data
- Detailed logging of link replacement process

### Understanding Mistral OCR Image Workflow
1. **API Detection**: Correctly finds images with coordinates
2. **Markdown Links**: Embeds references like `![alt](img-0.jpeg)` in markdown
3. **Base64 Data**: May be empty (`length=0`) for some documents
4. **Our Solution**: Links API metadata with markdown references and provides placeholders

### Previous Major Fixes
- **v2.0.5**: Professional SVG placeholders with visual design
- **v2.0.4**: NoneType error resolution with null-safe processing
- **v2.0.3**: Real API image support with markdown parsing
- **v2.0.2**: Complete image processing pipeline overhaul