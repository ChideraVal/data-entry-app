# import os
# import tempfile
# import pdfplumber
# import pytesseract
# from PIL import Image
# from openpyxl import load_workbook
# from docx import Document
# import csv
# import re
# import string
# from pathlib import Path

# def extract_text_from_file(file_obj):
#     """
#     Extracts text from high-priority file types:
#     - PDF (text + tables + OCR fallback)
#     - Images (jpg, jpeg, png)
#     - DOCX
#     - XLSX
#     - CSV
#     - Email body (string)
#     Returns cleaned text as a string (empty string if extraction fails)
#     """

#     def clean_text(text: str) -> str:
#         text = "".join(c for c in text if c in string.printable)
#         text = re.sub(r'\n\s*\n+', '\n', text)
#         return text.strip()

#     # If file_obj is just email body text (string)
#     # if isinstance(file_obj, str):
#     #     return clean_text(file_obj)


#     # filename = file_obj.name.lower()
#     file_obj = f"media/{file_obj}"
#     if not os.path.exists(file_obj):
#         print(f'FILE ({file_obj}) DOES NOT EXIST!')
#         return ""
#     ext = os.path.splitext(file_obj)[1]
#     print('EXT:', ext)

#     try:
#         text = ""

#         # -------------------------
#         # PDF
#         # -------------------------
#         if ext == ".pdf":
#             print('EXTRACTING PDF TEXT...')
#             try:
#                 with pdfplumber.open(file_obj) as pdf:
#                     for page in pdf.pages:
#                         # Extract normal page text
#                         page_text = page.extract_text() or ""
#                         text += page_text + "\n"

#                         # Extract tables
#                         tables = page.extract_tables()
#                         for table in tables:
#                             table_lines = []
#                             for row in table:
#                                 row_text = " | ".join([str(cell) for cell in row if cell is not None])
#                                 table_lines.append(row_text)
#                             text += "\n".join(table_lines) + "\n"

#                 # OCR fallback if text is empty
#                 if not text.strip():
#                     try:
#                         from pdf2image import convert_from_path
#                         images = convert_from_path(file_obj)
#                         for img in images:
#                             text += pytesseract.image_to_string(img) + "\n"
#                     except Exception:
#                         pass
#             except Exception:
#                 pass

#         # -------------------------
#         # Images
#         # -------------------------
#         elif ext in [".jpg", ".jpeg", ".png"]:
#             try:
#                 image = Image.open(file_obj)
#                 text = pytesseract.image_to_string(image)
#             except Exception:
#                 pass

#         # -------------------------
#         # DOCX
#         # -------------------------
#         elif ext == ".docx":
#             try:
#                 doc = Document(file_obj)
#                 text = "\n".join([p.text for p in doc.paragraphs])
#             except Exception:
#                 pass

#         # -------------------------
#         # XLSX
#         # -------------------------
#         elif ext == ".xlsx":
#             try:
#                 wb = load_workbook(file_obj, read_only=True)
#                 sheets_text = []
#                 for sheet in wb.sheetnames:
#                     ws = wb[sheet]
#                     for row in ws.iter_rows(values_only=True):
#                         line = " | ".join([str(cell) for cell in row if cell is not None])
#                         sheets_text.append(line)
#                 text = "\n".join(sheets_text)
#             except Exception:
#                 pass

#         # -------------------------
#         # CSV
#         # -------------------------
#         elif ext == ".csv":
#             try:
#                 file_obj.seek(0)
#                 decoded = file_obj.read().decode("utf-8")
#                 reader = csv.reader(decoded.splitlines())
#                 lines = []
#                 for row in reader:
#                     line = " | ".join([str(cell) for cell in row if cell])
#                     lines.append(line)
#                 text = "\n".join(lines)
#             except Exception:
#                 pass

#         # -------------------------
#         # Unsupported type
#         # -------------------------
#         # return clean_text(text)
#         return text
    
#     except Exception:
#         return ""



# from openai import OpenAI

# client = OpenAI(api_key="YOUR_OPENAI_API_KEY")  # Or use environment variable

# def ask_ai_validate(text: str) -> bool:
#     """
#     Asks AI if this text represents a valid invoice/purchase order.
#     Returns True/False
#     """
#     prompt = f"""
# You are an intelligent parser. Determine if the following text is a valid purchase order or invoice.
# Return only "YES" if it is, or "NO" if it is not.

# Text:
# {text}
# """
#     try:
#         response = client.chat.completions.create(
#             model="gpt-4",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0
#         )
#         answer = response.choices[0].message.content.strip().upper()
#         return "YES" in answer
#     except Exception as e:
#         # If AI fails, we treat as invalid
#         return False


# import json

# def ask_ai_extract_json(text: str) -> str:
#     """
#     Asks AI to extract structured JSON data from invoice/order text.
#     Returns a JSON string.
#     """
#     prompt = f"""
# You are an intelligent order parser. Extract structured JSON from the following invoice or purchase order.
# Return ONLY JSON in this format:

# {{
#   "supplier": "string",
#   "order_number": "string",
#   "date": "YYYY-MM-DD",
#   "items": [
#     {{
#       "sku": "string",
#       "description": "string",
#       "quantity": integer,
#       "unit_price": float,
#       "total_price": float
#     }}
#   ],
#   "total_amount": float,
#   "currency": "string"
# }}

# Text:
# {text}
# """
#     response = client.chat.completions.create(
#         model="gpt-4",
#         messages=[{"role": "user", "content": prompt}],
#         temperature=0
#     )
#     return response.choices[0].message.content.strip()



# def validate_order_json(order_data: dict) -> bool:
#     """
#     Checks required fields, types, and totals.
#     """
#     required_fields = ["supplier", "order_number", "date", "items", "total_amount", "currency"]
#     for f in required_fields:
#         if f not in order_data:
#             return False

#     if not isinstance(order_data["items"], list) or len(order_data["items"]) == 0:
#         return False

#     total_sum = 0
#     for item in order_data["items"]:
#         try:
#             qty = int(item["quantity"])
#             unit = float(item["unit_price"])
#             total = float(item["total_price"])
#             if abs(total - (qty * unit)) > 0.01:
#                 return False
#             total_sum += total
#         except Exception:
#             return False

#     if abs(total_sum - float(order_data["total_amount"])) > 0.01:
#         return False

#     return True


# def process_email(email_obj):
#     # 1. Combine email body + attachments
#     full_text = email_obj.body or ""
#     print(f"EMAIL BODY BELOW: ")
#     print("----------------------------------------")
#     print(full_text)
    
#     for attachment in email_obj.attachments:
#         text_from_file = extract_text_from_file(attachment["file_path"])
#         full_text += "\n" + text_from_file
        
#         print(f"FILE ({attachment["file_path"]}) FULL TEXT BELOW: ")
#         print("----------------------------------------")
#         print(text_from_file)

#     # 2. Validate invoice/order
#     # is_valid = ask_ai_validate(full_text)
#     # if not is_valid:
#     #     return False

#     # # 3. Extract JSON
#     # json_str = ask_ai_extract_json(full_text)
#     # try:
#     #     order_data = json.loads(json_str)
#     # except json.JSONDecodeError:
#     #     return False

#     # # 4. Validate JSON
#     # if not validate_order_json(order_data):
#     #     return False

#     # # 5. Save to database
#     # from ..models import ParsedOrder
#     # ParsedOrder.objects.create(
#     #     email=email_obj,
#     #     supplier=order_data["supplier"],
#     #     order_number=order_data["order_number"],
#     #     date=order_data["date"],
#     #     total_amount=order_data["total_amount"],
#     #     currency=order_data["currency"],
#     #     raw_json=order_data
#     # )
#     return True
