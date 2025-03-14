from mistralai import Mistral

api_key = "put your api key here"
client = Mistral(api_key=api_key)

from pathlib import Path

import argparse

# 创建命令行参数解析器
parser = argparse.ArgumentParser(description='处理PDF文件')
parser.add_argument('--pdf', type=str, default="demo-mistral.pdf", help='PDF file path')
args = parser.parse_args()

pdf_file = Path(args.pdf)
assert pdf_file.is_file()

from mistralai import DocumentURLChunk, ImageURLChunk, TextChunk,OCRResponse
import json

uploaded_file = client.files.upload(
    file={
        "file_name": pdf_file.stem,
        "content": pdf_file.read_bytes(),
    },
    purpose="ocr",
)

signed_url = client.files.get_signed_url(file_id=uploaded_file.id, expiry=1)

pdf_response = client.ocr.process(document=DocumentURLChunk(document_url=signed_url.url), model="mistral-ocr-latest", include_image_base64=True)

response_dict = json.loads(pdf_response.json())
#json_string = json.dumps(response_dict, indent=4)
#print(json_string)

def replace_images_in_markdown(markdown_str: str, images_dict: dict) -> str:
    for img_name, base64_str in images_dict.items():
        markdown_str = markdown_str.replace(f"![{img_name}]({img_name})", f"![{img_name}]({base64_str})")
    return markdown_str

def get_combined_markdown(ocr_response: OCRResponse) -> str:
  markdowns: list[str] = []
  for page in pdf_response.pages:
    image_data = {}
    for img in page.images:
      image_data[img.id] = img.image_base64
    markdowns.append(replace_images_in_markdown(page.markdown, image_data))

  return "\n\n".join(markdowns)

combined_markdown = get_combined_markdown(pdf_response)
print(combined_markdown)