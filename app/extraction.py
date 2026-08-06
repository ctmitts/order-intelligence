import pypdfium2 as pdfium  # permissive (BSD/Apache) PDF text + rendering
import base64
import pandas as pd
from anthropic import Anthropic
import json
from dotenv import load_dotenv
import time
from PIL import Image
import io
import os
import re

# Load environment variables
load_dotenv()

class HybridPackingSlipExtractor:
    def __init__(self):
        self.client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        
        # Text extraction prompt (optimized for clean text input)
        self.text_extraction_prompt = """
Extract order data from this order form text. Return ONLY a JSON array with this exact structure:

[
  {
    "Order_Number": "5182",
    "Date": "4/25/2024", 
    "Customer_Name": "Jennifer Sapienza",
    "Email": "jrsapienze@gmail.com",
    "Ship_Date": "4/26/2024",
    "Shipping_Address_Line1": "123 Main Street",
    "Shipping_Address_Line2": "Apt 4B",
    "Shipping_City": "New York",
    "Shipping_State": "NY",
    "Shipping_Zip": "10001",
    "Product_Code": "CARM-5",
    "Product_Description": "Cosmic Caramels - 5 Package (Save $100)",
    "Unit_Price": "149.99",
    "Quantity": "1", 
    "Extended_Price": "149.99",
    "Service_Fee": "8.58",
    "Total_Discount": "-30.00",
    "Sub_Total": "128.57",
    "Shipping": "12.00",
    "Total_Amount": "140.57"
  }
]

If multiple products on one order, create multiple objects with same order info but different product details.
Return ONLY the JSON array, no other text.
"""

        # Image extraction prompt (optimized for image analysis with name accuracy focus)
        self.image_extraction_prompt = """
Extract order data from this order form image. Pay special attention to customer names - read them carefully character by character.

IMPORTANT: For Customer_Name, look carefully at the text and ensure proper capitalization. Common name patterns:
- First name Last name (e.g., "Jennifer Sapienza", "John Smith", "Maria Rodriguez")
- Names may have apostrophes (e.g., "O'Connor", "D'Angelo") 
- Names may have hyphens (e.g., "Mary-Jane", "Jean-Paul")
- Look for names near shipping addresses or email addresses

Return ONLY a JSON array with this exact structure:

[
  {
    "Order_Number": "5182",
    "Date": "4/25/2024", 
    "Customer_Name": "Jennifer Sapienza",
    "Email": "jrsapienze@gmail.com",
    "Ship_Date": "4/26/2024",
    "Shipping_Address_Line1": "123 Main Street",
    "Shipping_Address_Line2": "Apt 4B",
    "Shipping_City": "New York",
    "Shipping_State": "NY",
    "Shipping_Zip": "10001",
    "Product_Code": "CARM-5",
    "Product_Description": "Cosmic Caramels - 5 Package (Save $100)",
    "Unit_Price": "149.99",
    "Quantity": "1", 
    "Extended_Price": "149.99",
    "Service_Fee": "8.58",
    "Total_Discount": "-30.00",
    "Sub_Total": "128.57",
    "Shipping": "12.00",
    "Total_Amount": "140.57"
  }
]

If multiple products on one order, create multiple objects with same order info but different product details.
Return ONLY the JSON array, no other text.
"""

    def has_sufficient_text(self, text):
        """Determine if text extraction yielded useful content"""
        if not text or len(text.strip()) < 50:
            return False
        
        # Remove excessive whitespace and check length again
        cleaned_text = re.sub(r'\s+', ' ', text.strip())
        if len(cleaned_text) < 30:
            return False
        
        # Check for meaningful content indicators
        order_keywords = ['order', 'customer', 'total', 'product', 'quantity', 'price', 'email', 'date']
        keyword_count = sum(1 for keyword in order_keywords if keyword.lower() in cleaned_text.lower())
        
        # Also check for currency symbols and dates
        has_currency = bool(re.search(r'\$\d+\.?\d*', text))
        has_date = bool(re.search(r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}', text))
        has_email = bool(re.search(r'\S+@\S+\.\S+', text))
        
        # Text is considered sufficient if we have multiple keywords or key indicators
        return keyword_count >= 3 or (keyword_count >= 2 and (has_currency or has_date or has_email))

    def extract_text_from_page(self, pdf_path, page_num):
        """Extract text from a PDF page (pypdfium2)."""
        pdf = None
        try:
            pdf = pdfium.PdfDocument(pdf_path)
            textpage = pdf[page_num].get_textpage()
            text_content = textpage.get_text_range().strip()
            return text_content
        except Exception as e:
            print(f"Error extracting text from page {page_num + 1}: {e}")
            return ""
        finally:
            if pdf is not None:
                pdf.close()

    def pdf_page_to_image(self, pdf_path, page_num):
        """Render a PDF page to an enhanced PIL Image for OCR (pypdfium2)."""
        pdf = None
        try:
            pdf = pdfium.PdfDocument(pdf_path)
            # scale=3 ≈ 216 DPI — higher resolution improves text recognition.
            bitmap = pdf[page_num].render(scale=3)
            image = bitmap.to_pil().convert("RGB")

            # Apply image enhancements for better OCR
            image = self._enhance_image_for_ocr(image)

            return image
        except Exception as e:
            print(f"Error converting page {page_num + 1} to image: {e}")
            return None
        finally:
            if pdf is not None:
                pdf.close()
    
    def _enhance_image_for_ocr(self, image):
        """Apply image enhancements to improve OCR accuracy"""
        from PIL import ImageEnhance, ImageFilter
        
        try:
            # Convert to RGB if not already
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Enhance contrast for better text recognition
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.2)  # Increase contrast by 20%
            
            # Enhance sharpness for crisper text
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.1)  # Slight sharpness increase
            
            # Apply a slight unsharp mask for text clarity
            image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=110, threshold=3))
            
            return image
            
        except Exception as e:
            print(f"Warning: Image enhancement failed: {e}")
            return image  # Return original if enhancement fails

    def _verify_customer_info(self, image, record, order_number):
        """Second pass verification for customer name, email, and address"""
        try:
            base64_image = self.image_to_base64(image)
            
            verification_prompt = f"""
This is a legitimate business packing slip for order fulfillment. You are helping with quality control for a business processing their own shipping documents.

TASK: Verify the accuracy of OCR text extraction from this business packing slip.

Current OCR results for Order #{order_number}:
- Customer Name: "{record.get('Customer_Name', '')}"
- Email: "{record.get('Email', '')}"  
- Address Line 1: "{record.get('Shipping_Address_Line1', '')}"
- Address Line 2: "{record.get('Shipping_Address_Line2', '')}"
- City: "{record.get('Shipping_City', '')}"
- State: "{record.get('Shipping_State', '')}"
- Zip: "{record.get('Shipping_Zip', '')}"

Please check the OCR accuracy and correct any errors. Read each field carefully from the image:

1. Customer name in the "Ship To:" section
2. Email address in contact information
3. Complete shipping address including apartment/unit numbers
4. City, state, and zip code

Return ONLY this JSON with corrected values:
{{
  "Customer_Name": "corrected name",
  "Email": "corrected@email.com", 
  "Shipping_Address_Line1": "123 Main Street",
  "Shipping_Address_Line2": "Apt 4B",
  "Shipping_City": "New York", 
  "Shipping_State": "NY",
  "Shipping_Zip": "10001"
}}"""

            # Constrain the response to a strict JSON schema so the model can't
            # preamble its way past the token budget (Opus narrates by default;
            # structured outputs guarantee the first text block is valid JSON).
            _verify_fields = [
                "Customer_Name", "Email", "Shipping_Address_Line1",
                "Shipping_Address_Line2", "Shipping_City", "Shipping_State",
                "Shipping_Zip",
            ]
            message = self.client.messages.create(
                model="claude-opus-4-8",
                max_tokens=400,
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": {
                            "type": "object",
                            "properties": {f: {"type": "string"} for f in _verify_fields},
                            "required": _verify_fields,
                            "additionalProperties": False,
                        },
                    }
                },
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": base64_image
                                }
                            },
                            {
                                "type": "text",
                                "text": verification_prompt
                            }
                        ]
                    }
                ]
            )
            
            response_text = message.content[0].text.strip()
            
            # Parse the JSON response
            import json
            try:
                # Try to extract JSON from response if it's embedded in other text
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_text = json_match.group()
                else:
                    json_text = response_text
                
                verification_data = json.loads(json_text)
                
                # Extract and validate all fields
                verified_name = verification_data.get('Customer_Name', record.get('Customer_Name', ''))
                verified_email = verification_data.get('Email', record.get('Email', ''))
                verified_addr1 = verification_data.get('Shipping_Address_Line1', record.get('Shipping_Address_Line1', ''))
                verified_addr2 = verification_data.get('Shipping_Address_Line2', record.get('Shipping_Address_Line2', ''))
                verified_city = verification_data.get('Shipping_City', record.get('Shipping_City', ''))
                verified_state = verification_data.get('Shipping_State', record.get('Shipping_State', ''))
                verified_zip = verification_data.get('Shipping_Zip', record.get('Shipping_Zip', ''))
                
                # Basic validation and update record
                if verified_name and 2 <= len(verified_name) <= 50:
                    record['Customer_Name'] = verified_name
                
                if verified_email and '@' in verified_email and '.' in verified_email:
                    record['Email'] = verified_email
                
                # Update address fields (less strict validation)
                if verified_addr1:
                    record['Shipping_Address_Line1'] = verified_addr1
                if verified_addr2:
                    record['Shipping_Address_Line2'] = verified_addr2
                if verified_city:
                    record['Shipping_City'] = verified_city
                if verified_state:
                    record['Shipping_State'] = verified_state
                if verified_zip:
                    record['Shipping_Zip'] = verified_zip
                    
            except json.JSONDecodeError as e:
                print(f"Could not parse verification response for order {order_number}")
                print(f"Response was: {response_text[:200]}...")
                print(f"JSON Error: {e}")
                
            return record
                
        except Exception as e:
            print(f"Customer info verification failed for order {order_number}: {e}")
            return record

    def image_to_base64(self, image):
        """Convert PIL image to base64"""
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

    def extract_from_text(self, text_content, page_num, source_file, pdf_page_num):
        """Extract data from text using Claude API"""
        try:
            message = self.client.messages.create(
                #model="claude-sonnet-4-20250514",
                model="claude-opus-4-8",
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": f"{self.text_extraction_prompt}\n\nText content:\n{text_content}"
                    }
                ]
            )
            
            response_text = message.content[0].text.strip()
            
            try:
                data = json.loads(response_text)
                # Add source tracking to each record
                for record in data:
                    record['Source_File'] = source_file
                    record['Source_Page'] = pdf_page_num
                return data
            except json.JSONDecodeError:
                print(f"Page {page_num}: Failed to parse JSON from text - {response_text[:100]}...")
                return []
                
        except Exception as e:
            print(f"Page {page_num}: Text API Error - {e}")
            return []

    def extract_from_image(self, image, page_num, source_file, pdf_page_num):
        """Extract data from image using Claude API"""
        try:
            base64_image = self.image_to_base64(image)
            
            message = self.client.messages.create(
                #model="claude-sonnet-4-20250514",
                model="claude-opus-4-8",
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": base64_image
                                }
                            },
                            {
                                "type": "text",
                                "text": self.image_extraction_prompt
                            }
                        ]
                    }
                ]
            )
            
            response_text = message.content[0].text.strip()
            
            try:
                data = json.loads(response_text)
                # Add source tracking and verify names/emails for each record
                for record in data:
                    record['Source_File'] = source_file
                    record['Source_Page'] = pdf_page_num
                    
                    # Second pass verification for customer info and address accuracy
                    if 'Customer_Name' in record and 'Email' in record and 'Order_Number' in record:
                        verified_record = self._verify_customer_info(
                            image, 
                            record,
                            record['Order_Number']
                        )
                        record.update(verified_record)
                        print(f"✓ Verified: {record['Customer_Name']}")
                        
                return data
            except json.JSONDecodeError:
                print(f"Page {page_num}: Failed to parse JSON from image - {response_text[:100]}...")
                return []
                
        except Exception as e:
            print(f"Page {page_num}: Image API Error - {e}")
            return []

    def extract_page_data(self, pdf_path, page_num, source_filename=None):
        """Hybrid extraction: try text first, fallback to image"""
        
        # Get source file name and page number for tracking
        source_file = source_filename if source_filename else os.path.basename(pdf_path)
        pdf_page_num = page_num + 1  # Convert to 1-indexed
        
        # First, try text extraction
        text_content = self.extract_text_from_page(pdf_path, page_num)
        
        if self.has_sufficient_text(text_content):
            print(f"📄 Using text extraction", end=' ')
            return self.extract_from_text(text_content, pdf_page_num, source_file, pdf_page_num)
        else:
            print(f"🖼️  Using image extraction", end=' ')
            image = self.pdf_page_to_image(pdf_path, page_num)
            if image is None:
                print("❌ Failed to convert to image")
                return []
            return self.extract_from_image(image, pdf_page_num, source_file, pdf_page_num)

    def process_pdf(self, pdf_path, output_csv_path, start_page=0, end_page=None):
        """Process PDF using hybrid approach"""
        print(f"Processing PDF: {pdf_path}")
        
        try:
            # Get page count
            doc = pdfium.PdfDocument(pdf_path)
            total_pages = len(doc)
            doc.close()
            
            print(f"Found {total_pages} pages")
            
            if end_page is None:
                end_page = total_pages
            else:
                end_page = min(end_page, total_pages)
            
            print(f"Processing pages {start_page + 1} to {end_page}")
            
            all_data = []
            text_pages = 0
            image_pages = 0
            
            for page_num in range(start_page, end_page):
                print(f"Page {page_num + 1}/{total_pages}: ", end='')
                
                # Use hybrid extraction
                page_data = self.extract_page_data(pdf_path, page_num)
                
                # Track which method was used (check the console output)
                # We'll increment counters based on what was printed
                
                if page_data:
                    all_data.extend(page_data)
                    print(f"✅ {len(page_data)} records")
                else:
                    print("❌ No data")
                
                # Save every 10 pages
                if len(all_data) > 0 and (page_num + 1) % 10 == 0:
                    self.save_data(all_data, output_csv_path)
                    print(f"  💾 Saved {len(all_data)} records so far")
                
                # Rate limiting
                time.sleep(0.5)
            
            # Final save
            if all_data:
                self.save_data(all_data, output_csv_path)
                print(f"\n🎉 COMPLETE: {len(all_data)} total records saved")
            else:
                print("\n❌ No data extracted from any pages")
                
        except Exception as e:
            print(f"Error processing PDF: {e}")

    def save_data(self, data, output_path):
        """Save data to CSV"""
        csv_headers = [
            'Order_Number', 'Date', 'Customer_Name', 'Email', 'Ship_Date',
            'Shipping_Address_Line1', 'Shipping_Address_Line2', 'Shipping_City', 
            'Shipping_State', 'Shipping_Zip', 'Product_Code', 'Product_Description', 
            'Unit_Price', 'Quantity', 'Extended_Price', 'Service_Fee', 'Total_Discount', 
            'Sub_Total', 'Shipping', 'Total_Amount', 'Source_File', 'Source_Page'
        ]
        
        df = pd.DataFrame(data)
        
        # Ensure all required columns exist
        for col in csv_headers:
            if col not in df.columns:
                df[col] = ''
        
        # Reorder columns
        df = df[csv_headers]
        df.to_csv(output_path, index=False)

def main():
    """Test the hybrid approach"""
    extractor = HybridPackingSlipExtractor()
    
    # Test with your PDF that had issues
    PDF_PATH = "samples/sample_order_form.pdf"
    OUTPUT_CSV = "extracted_orders.csv"
    
    # Test the problematic area where PyPDFLoader failed
    print("Testing hybrid extraction on the sample order form...")
    extractor.process_pdf(PDF_PATH, OUTPUT_CSV, start_page=0, end_page=2)

if __name__ == "__main__":
    main()