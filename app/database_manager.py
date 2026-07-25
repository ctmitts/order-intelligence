import chromadb
import pandas as pd
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional
import os

class OrderDatabaseManager:
    def __init__(self, db_path: str = "./chroma_db"):
        """Initialize ChromaDB for order record management"""
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection_name = "order_records"
        
        # Create or get collection
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
        except:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Order Form Records"}
            )
    
    def add_records(self, records: List[Dict], source_file: str = None) -> List[str]:
        """Add new order records to the database"""
        record_ids = []
        documents = []
        metadatas = []
        
        for record in records:
            # Generate unique ID
            record_id = str(uuid.uuid4())
            record_ids.append(record_id)
            
            # Create searchable document text
            doc_text = self._create_document_text(record)
            documents.append(doc_text)
            
            # Add metadata including all fields (clean order numbers)
            cleaned_order = self._clean_order_number(record.get("Order_Number", ""))
            metadata = {
                "order_number": str(cleaned_order) if cleaned_order is not None else "",
                "customer_name": str(record.get("Customer_Name", "")),
                "email": str(record.get("Email", "")),
                "date": str(record.get("Date", "")),
                "ship_date": str(record.get("Ship_Date", "")),
                "shipping_address_line1": str(record.get("Shipping_Address_Line1", "")),
                "shipping_address_line2": str(record.get("Shipping_Address_Line2", "")),
                "shipping_city": str(record.get("Shipping_City", "")),
                "shipping_state": str(record.get("Shipping_State", "")),
                "shipping_zip": str(record.get("Shipping_Zip", "")),
                "product_code": str(record.get("Product_Code", "")),
                "product_description": str(record.get("Product_Description", "")),
                "unit_price": str(record.get("Unit_Price", "")),
                "quantity": str(record.get("Quantity", "")),
                "extended_price": str(record.get("Extended_Price", "")),
                "service_fee": str(record.get("Service_Fee", "")),
                "total_discount": str(record.get("Total_Discount", "")),
                "sub_total": str(record.get("Sub_Total", "")),
                "shipping": str(record.get("Shipping", "")),
                "total_amount": str(record.get("Total_Amount", "")),
                "source_file": record.get("Source_File", source_file or "unknown"),
                "source_page": str(record.get("Source_Page", "")),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            metadatas.append(metadata)
        
        # Add to collection
        self.collection.add(
            ids=record_ids,
            documents=documents,
            metadatas=metadatas
        )
        
        return record_ids
    
    def _clean_order_number(self, order_num):
        """Clean order number to remove .0 and return as integer or NaN"""
        import pandas as pd
        
        if not order_num or pd.isna(order_num):
            return pd.NA
        
        try:
            # Convert to float first to handle both "12440" and "12440.0"
            num = float(str(order_num))
            # Convert to int to remove decimal
            return int(num)
        except (ValueError, TypeError):
            # If conversion fails, return NaN
            return pd.NA
    
    def clean_existing_order_numbers(self):
        """Clean up existing order numbers in the database to remove .0 suffixes"""
        print("🧹 Cleaning existing order numbers...")
        
        # Get all records
        all_records = self.collection.get()
        
        if not all_records['ids']:
            print("No records found to clean.")
            return
        
        updated_count = 0
        
        for i, record_id in enumerate(all_records['ids']):
            metadata = all_records['metadatas'][i]
            current_order_num = metadata.get('order_number', '')
            
            # Clean the order number
            cleaned_order_num = self._clean_order_number(current_order_num)
            
            # Only update if it changed
            if cleaned_order_num != current_order_num:
                metadata['order_number'] = cleaned_order_num
                metadata['updated_at'] = datetime.now().isoformat()
                
                # Update the record
                self.collection.update(
                    ids=[record_id],
                    metadatas=[metadata]
                )
                updated_count += 1
                
                if updated_count % 100 == 0:
                    print(f"  Cleaned {updated_count} records so far...")
        
        print(f"✅ Cleaned {updated_count} order numbers (removed .0 suffixes)")
        return updated_count
    
    def _create_document_text(self, record: Dict) -> str:
        """Create searchable text from record data"""
        searchable_fields = [
            record.get("Order_Number", ""),
            record.get("Customer_Name", ""),
            record.get("Email", ""),
            record.get("Shipping_Address_Line1", ""),
            record.get("Shipping_City", ""),
            record.get("Shipping_State", ""),
            record.get("Shipping_Zip", ""),
            record.get("Product_Code", ""),
            record.get("Product_Description", ""),
        ]
        return " ".join(str(field) for field in searchable_fields if field)
    
    def search_records(self, query: str, limit: int = 100) -> pd.DataFrame:
        """Search records by order number, name, email, or general text"""
        if not query.strip():
            return self.get_all_records(limit=limit)
        
        query = query.strip()
        
        # Try exact matches first for common search patterns
        exact_results = []
        
        # 1. Try exact order number match
        if query.isdigit():
            order_results = self.collection.get(
                where={"order_number": query},
                limit=limit
            )
            if order_results['ids']:
                return self._metadata_to_dataframe(order_results)
        
        # 2. Try email match (contains @ symbol)
        if '@' in query:
            email_results = self.collection.get(
                where={"email": {"$eq": query}},
                limit=limit
            )
            if email_results['ids']:
                return self._metadata_to_dataframe(email_results)
        
        # 3. Try partial matching using get with contains-like logic
        # Get all records and filter in pandas for better control
        all_records = self.get_all_records()
        if all_records.empty:
            return all_records
        
        # Create case-insensitive search across key fields
        query_lower = query.lower()
        mask = (
            all_records['Order_Number'].astype(str).str.lower().str.contains(query_lower, na=False) |
            all_records['Customer_Name'].astype(str).str.lower().str.contains(query_lower, na=False) |
            all_records['Email'].astype(str).str.lower().str.contains(query_lower, na=False) |
            all_records['Shipping_Address_Line1'].astype(str).str.lower().str.contains(query_lower, na=False) |
            all_records['Shipping_City'].astype(str).str.lower().str.contains(query_lower, na=False) |
            all_records['Shipping_State'].astype(str).str.lower().str.contains(query_lower, na=False) |
            all_records['Shipping_Zip'].astype(str).str.lower().str.contains(query_lower, na=False) |
            all_records['Product_Code'].astype(str).str.lower().str.contains(query_lower, na=False) |
            all_records['Product_Description'].astype(str).str.lower().str.contains(query_lower, na=False)
        )
        
        filtered_results = all_records[mask]
        
        # Sort by relevance: exact order number matches first, then name matches, then others
        if not filtered_results.empty:
            # Prioritize exact order number matches
            exact_order = filtered_results[
                filtered_results['Order_Number'].astype(str).str.lower() == query_lower
            ]
            # Then partial order number matches
            partial_order = filtered_results[
                (filtered_results['Order_Number'].astype(str).str.lower().str.contains(query_lower, na=False)) &
                (filtered_results['Order_Number'].astype(str).str.lower() != query_lower)
            ]
            # Then name/email matches
            other_matches = filtered_results[
                ~filtered_results['Order_Number'].astype(str).str.lower().str.contains(query_lower, na=False)
            ]
            
            # Combine in priority order
            prioritized_results = pd.concat([exact_order, partial_order, other_matches], ignore_index=True)
            return prioritized_results.head(limit)
        
        return pd.DataFrame()
    
    def get_all_records(self, limit: int = None) -> pd.DataFrame:
        """Get all records from the database"""
        results = self.collection.get(limit=limit)
        return self._metadata_to_dataframe(results)
    
    def get_records_by_filter(self, filters: Dict = None, limit: int = None) -> pd.DataFrame:
        """Get records with specific filters"""
        where_clause = {}
        if filters:
            for key, value in filters.items():
                if value:  # Only add non-empty filters
                    where_clause[key] = value
        
        if where_clause:
            results = self.collection.get(where=where_clause, limit=limit)
        else:
            results = self.collection.get(limit=limit)
        
        return self._metadata_to_dataframe(results)
    
    def update_record(self, record_id: str, updated_data: Dict) -> bool:
        """Update a specific record"""
        try:
            # Get existing record
            existing = self.collection.get(ids=[record_id])
            if not existing['ids']:
                return False
            
            # Update metadata
            existing_metadata = existing['metadatas'][0]
            for key, value in updated_data.items():
                # Convert field names to metadata keys
                metadata_key = key.lower().replace('_', '_')
                existing_metadata[metadata_key] = str(value)
            
            existing_metadata['updated_at'] = datetime.now().isoformat()
            
            # Update document text
            doc_text = self._create_document_text(updated_data)
            
            # Update in collection
            self.collection.update(
                ids=[record_id],
                documents=[doc_text],
                metadatas=[existing_metadata]
            )
            return True
        except Exception as e:
            print(f"Error updating record: {e}")
            return False
    
    def delete_record(self, record_id: str) -> bool:
        """Delete a specific record"""
        try:
            self.collection.delete(ids=[record_id])
            return True
        except Exception as e:
            print(f"Error deleting record: {e}")
            return False
    
    def _results_to_dataframe(self, results) -> pd.DataFrame:
        """Convert ChromaDB query results to DataFrame"""
        if not results['ids'] or not results['ids'][0]:
            return pd.DataFrame()
        
        records = []
        for i, record_id in enumerate(results['ids'][0]):
            metadata = results['metadatas'][0][i]
            record = {
                'id': record_id,
                'Order_Number': metadata.get('order_number', ''),
                'Date': metadata.get('date', ''),
                'Customer_Name': metadata.get('customer_name', ''),
                'Email': metadata.get('email', ''),
                'Ship_Date': metadata.get('ship_date', ''),
                'Shipping_Address_Line1': metadata.get('shipping_address_line1', ''),
                'Shipping_Address_Line2': metadata.get('shipping_address_line2', ''),
                'Shipping_City': metadata.get('shipping_city', ''),
                'Shipping_State': metadata.get('shipping_state', ''),
                'Shipping_Zip': metadata.get('shipping_zip', ''),
                'Product_Code': metadata.get('product_code', ''),
                'Product_Description': metadata.get('product_description', ''),
                'Unit_Price': metadata.get('unit_price', ''),
                'Quantity': metadata.get('quantity', ''),
                'Extended_Price': metadata.get('extended_price', ''),
                'Service_Fee': metadata.get('service_fee', ''),
                'Total_Discount': metadata.get('total_discount', ''),
                'Sub_Total': metadata.get('sub_total', ''),
                'Shipping': metadata.get('shipping', ''),
                'Total_Amount': metadata.get('total_amount', ''),
                'Source_File': metadata.get('source_file', ''),
                'Source_Page': metadata.get('source_page', ''),
                'Created_At': metadata.get('created_at', ''),
                'Updated_At': metadata.get('updated_at', '')
            }
            records.append(record)
        
        return pd.DataFrame(records)
    
    def _metadata_to_dataframe(self, results) -> pd.DataFrame:
        """Convert ChromaDB get results to DataFrame"""
        if not results['ids']:
            return pd.DataFrame()
        
        records = []
        for i, record_id in enumerate(results['ids']):
            metadata = results['metadatas'][i]
            record = {
                'id': record_id,
                'Order_Number': metadata.get('order_number', ''),
                'Date': metadata.get('date', ''),
                'Customer_Name': metadata.get('customer_name', ''),
                'Email': metadata.get('email', ''),
                'Ship_Date': metadata.get('ship_date', ''),
                'Shipping_Address_Line1': metadata.get('shipping_address_line1', ''),
                'Shipping_Address_Line2': metadata.get('shipping_address_line2', ''),
                'Shipping_City': metadata.get('shipping_city', ''),
                'Shipping_State': metadata.get('shipping_state', ''),
                'Shipping_Zip': metadata.get('shipping_zip', ''),
                'Product_Code': metadata.get('product_code', ''),
                'Product_Description': metadata.get('product_description', ''),
                'Unit_Price': metadata.get('unit_price', ''),
                'Quantity': metadata.get('quantity', ''),
                'Extended_Price': metadata.get('extended_price', ''),
                'Service_Fee': metadata.get('service_fee', ''),
                'Total_Discount': metadata.get('total_discount', ''),
                'Sub_Total': metadata.get('sub_total', ''),
                'Shipping': metadata.get('shipping', ''),
                'Total_Amount': metadata.get('total_amount', ''),
                'Source_File': metadata.get('source_file', ''),
                'Source_Page': metadata.get('source_page', ''),
                'Created_At': metadata.get('created_at', ''),
                'Updated_At': metadata.get('updated_at', '')
            }
            records.append(record)
        
        return pd.DataFrame(records)
    
    def get_summary_stats(self) -> Dict:
        """Get database summary statistics"""
        all_records = self.get_all_records()
        
        if all_records.empty:
            return {"total_records": 0}
        
        stats = {
            "total_records": len(all_records),
            "unique_orders": all_records['Order_Number'].nunique(),
            "unique_customers": all_records['Customer_Name'].nunique(),
            "date_range": {
                "earliest": all_records['Date'].min(),
                "latest": all_records['Date'].max()
            },
            "top_products": all_records['Product_Code'].value_counts().head(5).to_dict(),
            "source_files": all_records['Source_File'].value_counts().to_dict()
        }
        
        return stats
    
    def export_to_csv(self, df: pd.DataFrame, filename: str = None) -> str:
        """Export DataFrame to CSV and return the data"""
        # Remove internal fields for export
        export_columns = [
            'Order_Number', 'Date', 'Customer_Name', 'Email', 'Ship_Date',
            'Shipping_Address_Line1', 'Shipping_Address_Line2', 'Shipping_City', 
            'Shipping_State', 'Shipping_Zip', 'Product_Code', 'Product_Description', 
            'Unit_Price', 'Quantity', 'Extended_Price', 'Service_Fee', 'Total_Discount', 
            'Sub_Total', 'Shipping', 'Total_Amount', 'Source_File', 'Source_Page'
        ]
        
        export_df = df[export_columns] if not df.empty else pd.DataFrame(columns=export_columns)
        return export_df.to_csv(index=False)