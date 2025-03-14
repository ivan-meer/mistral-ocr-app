const htmlForm = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mistral OCR PDF to Markdown Converter</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      max-width: 800px;
      margin: 0 auto;
      padding: 20px;
    }
    h1 {
      color: #2c3e50;
      margin-bottom: 20px;
    }
    .container {
      background-color: #f9f9f9;
      border-radius: 8px;
      padding: 20px;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
    }
    .form-group {
      margin-bottom: 20px;
    }
    label {
      display: block;
      margin-bottom: 8px;
      font-weight: bold;
    }
    input[type="text"], input[type="file"], input[type="url"], input[type="password"] {
      width: 100%;
      padding: 10px;
      border: 1px solid #ddd;
      border-radius: 4px;
      box-sizing: border-box;
    }
    button {
      background-color: #3498db;
      color: white;
      border: none;
      padding: 12px 20px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 16px;
      transition: background-color 0.3s;
    }
    button:hover {
      background-color: #2980b9;
    }
    .api-key-info {
      margin-top: 20px;
      padding: 15px;
      background-color: #e8f4f8;
      border-radius: 4px;
      font-size: 14px;
    }
    #status {
      margin-top: 20px;
      padding: 10px;
      border-radius: 4px;
      display: none;
    }
    .loading {
      display: inline-block;
      width: 20px;
      height: 20px;
      border: 3px solid rgba(0, 0, 0, 0.1);
      border-radius: 50%;
      border-top-color: #3498db;
      animation: spin 1s ease-in-out infinite;
      margin-right: 10px;
      vertical-align: middle;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    .api-key-container {
      display: flex;
      gap: 10px;
      align-items: flex-end;
    }
    .save-key-btn {
      background-color: #27ae60;
      color: white;
      border: none;
      padding: 10px 15px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
      transition: background-color 0.3s;
      white-space: nowrap;
    }
    .save-key-btn:hover {
      background-color: #219653;
    }
    .saved-key-info {
      font-size: 14px;
      color: #27ae60;
      margin-top: 5px;
      display: none;
    }
    /* Tab styles */
    .tabs {
      display: flex;
      margin-bottom: 20px;
      border-bottom: 1px solid #ddd;
    }
    .tab {
      padding: 10px 20px;
      cursor: pointer;
      background-color: #f1f1f1;
      border: 1px solid #ddd;
      border-bottom: none;
      margin-right: 5px;
      border-radius: 4px 4px 0 0;
    }
    .tab.active {
      background-color: #fff;
      border-bottom: 1px solid #fff;
      margin-bottom: -1px;
    }
    .tab-content {
      display: none;
    }
    .tab-content.active {
      display: block;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Mistral OCR PDF to Markdown Converter</h1>
    
    <form id="pdfForm">
      <div class="form-group">
        <label for="apiKey">Mistral API key</label>
        <div class="api-key-container">
          <input type="password" id="apiKey" name="apiKey" required placeholder="Enter your Mistral API key">
          <button type="button" id="saveKeyBtn" class="save-key-btn">Save API Key</button>
        </div>
        <div id="savedKeyInfo" class="saved-key-info">API Key saved locally, will be auto-filled next time</div>
      </div>
      
      <!-- Input Method Tabs -->
      <div class="tabs">
        <div class="tab active" data-tab="fileUpload">Upload File</div>
        <div class="tab" data-tab="urlInput">URL Input</div>
      </div>
      
      <!-- File Upload Tab Content -->
      <div id="fileUpload" class="tab-content active">
        <div class="form-group">
          <label for="pdfFile">Upload PDF file</label>
          <input type="file" id="pdfFile" name="pdfFile" accept=".pdf">
        </div>
      </div>
      
      <!-- URL Input Tab Content -->
      <div id="urlInput" class="tab-content">
        <div class="form-group">
          <label for="pdfUrl">PDF URL</label>
          <input type="url" id="pdfUrl" name="pdfUrl" placeholder="Enter URL to PDF file (e.g., https://example.com/document.pdf)">
        </div>
      </div>
      
      <button type="submit" id="submitBtn">Convert and Download Markdown</button>
    </form>
    
    <div id="status"></div>
    
    <div class="api-key-info">
      <p><strong>Note:</strong> Your API key is only used for this session. If you choose to save it, it will be stored only in your browser locally and not sent to the server.</p>
    </div>
  </div>
  
  <script>
    // Check for saved API Key on page load
    document.addEventListener('DOMContentLoaded', function() {
      const savedApiKey = localStorage.getItem('mistralApiKey');
      const apiKeyInput = document.getElementById('apiKey');
      const savedKeyInfo = document.getElementById('savedKeyInfo');
      
      if (savedApiKey) {
        apiKeyInput.value = savedApiKey;
        savedKeyInfo.style.display = 'block';
      }
      
      // Tab functionality
      const tabs = document.querySelectorAll('.tab');
      tabs.forEach(tab => {
        tab.addEventListener('click', () => {
          // Remove active class from all tabs and contents
          document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
          document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
          
          // Add active class to clicked tab and corresponding content
          tab.classList.add('active');
          document.getElementById(tab.dataset.tab).classList.add('active');
        });
      });
    });
    
    // Save API Key functionality
    document.getElementById('saveKeyBtn').addEventListener('click', function() {
      const apiKey = document.getElementById('apiKey').value;
      const savedKeyInfo = document.getElementById('savedKeyInfo');
      
      if (apiKey) {
        localStorage.setItem('mistralApiKey', apiKey);
        savedKeyInfo.style.display = 'block';
        alert('API Key successfully saved!');
      } else {
        alert('Please enter an API Key first');
      }
    });

    document.getElementById('pdfForm').addEventListener('submit', async function(e) {
      e.preventDefault();
      
      const apiKey = document.getElementById('apiKey').value;
      const pdfFile = document.getElementById('pdfFile').files[0];
      const pdfUrl = document.getElementById('pdfUrl').value;
      const statusDiv = document.getElementById('status');
      const submitBtn = document.getElementById('submitBtn');
      const activeTab = document.querySelector('.tab.active').dataset.tab;
      
      if (!apiKey) {
        statusDiv.style.display = 'block';
        statusDiv.style.backgroundColor = '#ffdddd';
        statusDiv.innerHTML = 'Please enter your Mistral API key';
        return;
      }
      
      if (activeTab === 'fileUpload' && !pdfFile) {
        statusDiv.style.display = 'block';
        statusDiv.style.backgroundColor = '#ffdddd';
        statusDiv.innerHTML = 'Please upload a PDF file';
        return;
      }
      
      if (activeTab === 'urlInput' && !pdfUrl) {
        statusDiv.style.display = 'block';
        statusDiv.style.backgroundColor = '#ffdddd';
        statusDiv.innerHTML = 'Please enter a PDF URL';
        return;
      }
      
      // Show loading status
      statusDiv.style.display = 'block';
      statusDiv.style.backgroundColor = '#e8f4f8';
      statusDiv.innerHTML = '<div class="loading"></div> Processing PDF file, please wait...';
      submitBtn.disabled = true;
      
      const formData = new FormData();
      formData.append('apiKey', apiKey);
      formData.append('inputType', activeTab);
      
      if (activeTab === 'fileUpload') {
        formData.append('pdfFile', pdfFile);
      } else {
        formData.append('pdfUrl', pdfUrl);
      }
      
      try {
        const response = await fetch('/convert', {
          method: 'POST',
          body: formData
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText || 'Error occurred during conversion');
        }
        
        // Check if Content-Type is text/plain
        const contentType = response.headers.get('Content-Type');
        if (contentType && contentType.includes('text/plain')) {
          // Create Blob and download
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.style.display = 'none';
          a.href = url;
          
          // Use the file name from upload, or extract from URL, or use default
          let fileName = 'document.md';
          if (activeTab === 'fileUpload' && pdfFile) {
            fileName = pdfFile.name.replace('.pdf', '.md');
          } else if (activeTab === 'urlInput' && pdfUrl) {
            const urlParts = pdfUrl.split('/');
            const lastPart = urlParts[urlParts.length - 1];
            if (lastPart && lastPart.includes('.pdf')) {
              fileName = lastPart.replace('.pdf', '.md');
            }
          }
          
          a.download = fileName;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          
          statusDiv.style.backgroundColor = '#ddffdd';
          statusDiv.innerHTML = 'Conversion successful! Markdown file has been downloaded.';
        } else {
          // Handle error response
          const errorText = await response.text();
          throw new Error(errorText || 'Error occurred during download');
        }
      } catch (error) {
        statusDiv.style.backgroundColor = '#ffdddd';
        statusDiv.innerHTML = 'Error: ' + error.message;
      } finally {
        submitBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
`;

async function handleRequest(request) {
  const url = new URL(request.url);
  
  // Handle home/upload page request
  if (url.pathname === '/' && request.method === 'GET') {
    return new Response(htmlForm, {
      headers: {
        'Content-Type': 'text/html;charset=UTF-8',
      },
    });
  }
  
  // Handle PDF conversion request
  if (url.pathname === '/convert' && request.method === 'POST') {
    const formData = await request.formData();
    const apiKey = formData.get('apiKey');
    const inputType = formData.get('inputType');
    
    if (!apiKey) {
      return new Response('Missing API key', { status: 400 });
    }
    
    try {
      let ocrResponse;
      let filename = 'document.md';
      
      // Process based on input type
      if (inputType === 'fileUpload') {
        const pdfFile = formData.get('pdfFile');
        if (!pdfFile) {
          return new Response('Missing PDF file', { status: 400 });
        }
        
        // 1. Upload PDF file to Mistral API
        const uploadResponse = await uploadFileToMistral(apiKey, pdfFile);
        const fileId = uploadResponse.id;
        
        // 2. Get signed URL
        const signedUrlResponse = await getSignedUrl(apiKey, fileId);
        const signedUrl = signedUrlResponse.url;
        
        // 3. Call OCR API to process document
        ocrResponse = await processOcr(apiKey, signedUrl);
        
        // Set filename based on uploaded file
        filename = pdfFile.name.replace('.pdf', '.md');
      } else if (inputType === 'urlInput') {
        const pdfUrl = formData.get('pdfUrl');
        if (!pdfUrl) {
          return new Response('Missing PDF URL', { status: 400 });
        }
        
        // Process OCR directly with URL
        ocrResponse = await processOcrWithUrl(apiKey, pdfUrl);
        
        // Try to extract filename from URL
        try {
          const urlParts = new URL(pdfUrl).pathname.split('/');
          const lastPart = urlParts[urlParts.length - 1];
          if (lastPart && lastPart.includes('.pdf')) {
            filename = lastPart.replace('.pdf', '.md');
          }
        } catch (e) {
          // If URL parsing fails, keep default filename
          console.error('Error parsing URL for filename:', e);
        }
      } else {
        return new Response('Invalid input type', { status: 400 });
      }
      
      // 4. Extract and merge Markdown
      const markdown = getCombinedMarkdown(ocrResponse);
      
      // 5. Return Markdown as a downloadable file
      return new Response(markdown, {
        headers: {
          'Content-Type': 'text/plain;charset=UTF-8',
          'Content-Disposition': `attachment; filename="${filename}"`,
        },
      });
    } catch (error) {
      console.error('Error occurred:', error);
      return new Response(`Error occurred during conversion: ${error.message}`, { status: 500 });
    }
  }
  
  // Handle other paths
  return new Response('Not found', { status: 404 });
}

/**
 * Upload file to Mistral API
 */
async function uploadFileToMistral(apiKey, file) {
  const formData = new FormData();
  formData.append('purpose', 'ocr');
  formData.append('file', file);
  
  const response = await fetch('https://api.mistral.ai/v1/files', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
    },
    body: formData,
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to upload file: ${errorText}`);
  }
  
  return await response.json();
}

/**
 * Get signed URL
 */
async function getSignedUrl(apiKey, fileId, expiry = 24) {
  const response = await fetch(`https://api.mistral.ai/v1/files/${fileId}/url?expiry=${expiry}`, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
    },
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to get signed URL: ${errorText}`);
  }
  
  return await response.json();
}

/**
 * Process OCR request - use signed URL to call OCR API
 */
async function processOcr(apiKey, signedUrl) {
  const response = await fetch('https://api.mistral.ai/v1/ocr', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: "mistral-ocr-latest",
      document: {
        type: "document_url",
        document_url: signedUrl,
      },
      include_image_base64: true
    }),
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OCR processing failed: ${errorText}`);
  }
  
  return await response.json();
}

/**
 * Process OCR request directly with document URL
 */
async function processOcrWithUrl(apiKey, documentUrl) {
  const response = await fetch('https://api.mistral.ai/v1/ocr', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: "mistral-ocr-latest",
      document: {
        type: "document_url",
        document_url: documentUrl,
      },
      include_image_base64: true
    }),
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OCR processing failed: ${errorText}`);
  }
  
  return await response.json();
}

/**
 * Replace image references in Markdown with base64 images
 */
function replaceImagesInMarkdown(markdownStr, imagesDict) {
  for (const [imgName, base64Str] of Object.entries(imagesDict)) {
    markdownStr = markdownStr.replace(
      new RegExp(`!\\[${imgName}\\]\\(${imgName}\\)`, 'g'), 
      `![${imgName}](${base64Str})`
    );
  }
  return markdownStr;
}

/**
 * Merge all pages' Markdown - reference to the merge logic in main.py
 */
function getCombinedMarkdown(ocrResponse) {
  const markdowns = [];
  
  for (const page of ocrResponse.pages) {
    const imageData = {};
    if (page.images) {
      for (const img of page.images) {
        imageData[img.id] = img.image_base64;
      }
    }
    markdowns.push(replaceImagesInMarkdown(page.markdown, imageData));
  }
  
  return markdowns.join('\n\n');
}

// Listen for requests
addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
}); 