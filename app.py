import streamlit as st
from streamlit_option_menu import option_menu
import json
import os
import base64
import time
import datetime
from PIL import Image
import io
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import tempfile
import hashlib
import uuid
import re
import zipfile


# =============================================
# Streamlit Configuration
# =============================================

# Set page config
st.set_page_config(
    page_title="Inventory Management System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for consistent styling
st.markdown("""
    <style>
        body {
            font-family: Arial, sans-serif;
        }
        .stButton button {
            transition: all 0.3s;
        }
        .stButton button:hover {
            transform: translateY(-2px);
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }
        .stDataFrame {
            border-radius: 8px;
        }
        [data-testid="stExpander"] {
            border-radius: 8px;
            border: 1px solid rgba(0,0,0,0.1);
        }
        .stAlert {
            border-radius: 8px;
        }
        .sidebar .sidebar-content {
            background-color: #f8f9fa;
        }
    </style>
""", unsafe_allow_html=True)

# =============================================
# Data Storage & Encryption (JSON-based)
# =============================================

class JSONDatabase:
    # ... existing code ...
    
    def get_inventory_items(self):
        """Get all inventory items"""
        return self.data['inventory']
    
    def get_inventory_item(self, item_id: str):
        """Get a specific inventory item by ID"""
        return next((item for item in self.data['inventory'] if item['id'] == item_id), None)
    
    def add_inventory_item(self, item_data: dict):
        """Add a new inventory item"""
        try:
            item_data['id'] = str(uuid.uuid4())
            item_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['inventory'].append(item_data)
            self._save_data()
            return item_data['id']
        except Exception as e:
            st.error(f"Error adding inventory item: {e}")
            return None
    
    def update_inventory_item(self, item_id: str, update_data: dict):
        """Update an inventory item"""
        item = next((i for i in self.data['inventory'] if i['id'] == item_id), None)
        if item:
            item.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_inventory_item(self, item_id: str):
        """Delete an inventory item"""
        try:
            self.data['inventory'] = [i for i in self.data['inventory'] if i['id'] != item_id]
            self._save_data()
            return True, "Item deleted successfully"
        except Exception as e:
            return False, f"Error deleting item: {e}"
    
    def get_inventory_item_by_barcode(self, barcode: str):
        """Get inventory item by barcode"""
        return next((item for item in self.data['inventory'] if item.get('barcode') == barcode), None)

        
    def add_inventory_location(self, location_data: dict):
        """Add inventory to a specific location"""
        try:
            location_data['id'] = str(uuid.uuid4())
            location_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['inventory_locations'].append(location_data)
            self._save_data()
            return location_data['id']
        except Exception as e:
            st.error(f"Error adding inventory location: {e}")
            return None
    
    def get_inventory_locations(self, product_id: str = None, location_id: str = None):
        """Get inventory locations, optionally filtered by product or location"""
        if product_id and location_id:
            return [il for il in self.data['inventory_locations'] 
                   if il['product_id'] == product_id and il['location_id'] == location_id]
        elif product_id:
            return [il for il in self.data['inventory_locations'] if il['product_id'] == product_id]
        elif location_id:
            return [il for il in self.data['inventory_locations'] if il['location_id'] == location_id]
        return self.data['inventory_locations']
    
    def update_inventory_location(self, location_id: str, update_data: dict):
        """Update an inventory location"""
        location = next((il for il in self.data['inventory_locations'] if il['id'] == location_id), None)
        if location:
            location.update(update_data)
            self._save_data()
            return True
        return False
    
    def get_total_inventory_by_product(self, product_id: str):
        """Get total inventory across all locations for a product"""
        locations = self.get_inventory_locations(product_id=product_id)
        return sum(loc['quantity'] for loc in locations)
    
    def transfer_inventory(self, product_id: str, from_location_id: str, 
                          to_location_id: str, quantity: int, reason: str = ""):
        """Transfer inventory between locations"""
        try:
            # Check if source has enough inventory
            source_loc = next((il for il in self.get_inventory_locations(product_id, from_location_id)), None)
            if not source_loc or source_loc['quantity'] < quantity:
                return False, "Not enough inventory at source location"
            
            # Update source location
            self.update_inventory_location(source_loc['id'], {
                'quantity': source_loc['quantity'] - quantity
            })
            
            # Update or create destination location
            dest_loc = next((il for il in self.get_inventory_locations(product_id, to_location_id)), None)
            if dest_loc:
                self.update_inventory_location(dest_loc['id'], {
                    'quantity': dest_loc['quantity'] + quantity
                })
            else:
                self.add_inventory_location({
                    'product_id': product_id,
                    'location_id': to_location_id,
                    'quantity': quantity
                })
            
            # Log the transfer
            self.log_audit(
                st.session_state.user_id,
                "inventory_transfer",
                f"Transferred {quantity} units of {product_id} from {from_location_id} to {to_location_id}. Reason: {reason}"
            )
            
            return True, "Inventory transferred successfully"
        except Exception as e:
            return False, f"Error transferring inventory: {e}"
        
    def __init__(self, db_path: str = "inventory_data.json"):
        self.db_path = db_path
        self.data = self._load_data()
        self._initialize_db()
        
    def _load_data(self) -> dict:
        """Load data from JSON file or create new if doesn't exist"""
        try:
            if os.path.exists(self.db_path):
                with open(self.db_path, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            st.error(f"Error loading database: {e}")
            return {}
    
    def _save_data(self):
        """Save data to JSON file"""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(self.data, f, indent=4)
            return True
        except Exception as e:
            st.error(f"Error saving database: {e}")
            return False
    
    def _initialize_db(self):
        """Initialize database with default structure if empty"""
        if not self.data:
            self.data = {
                'users': [],
                'inventory': [],
                'suppliers': [],
                'customers': [],
                'transactions': [],
                'invoices': [],
                'invoice_items': [],
                'audit_log': [],
                'system_settings': [],
                'backups': [],
                'categories': [],
                'subcategories': [],
                'brands': [],
                'locations': [],
                'product_images': [],
                'bank_accounts': [],
                'payments': [],
                'tax_rates': [],
                'unknown_products': [],
                'reports': []
            }
            
            # Create default admin user with hashed password
            self.add_user({
                'username': 'admin',
                'password': 'admin123',  # Will be hashed in add_user
                'role': 'Admin',
                'email': 'admin@inventory.com',
                'is_active': True
            })
            
            # Add default system settings
            default_settings = [
                {"setting_name": "company_name", "setting_value": "My Inventory Inc.", "description": "Company name"},
                {"setting_name": "company_address", "setting_value": "123 Business St, City", "description": "Company address"},
                {"setting_name": "company_phone", "setting_value": "+1 234 567 8900", "description": "Company phone"},
                {"setting_name": "company_email", "setting_value": "info@myinventory.com", "description": "Company email"},
                {"setting_name": "company_logo", "setting_value": "", "description": "Path to company logo"},
                {"setting_name": "invoice_prefix", "setting_value": "INV", "description": "Invoice prefix"},
                {"setting_name": "invoice_header", "setting_value": "INVOICE", "description": "Invoice header text"},
                {"setting_name": "invoice_subheader", "setting_value": "Thank you for your business", "description": "Invoice subheader"},
                {"setting_name": "invoice_footer", "setting_value": "Terms & Conditions: Payment due within 30 days", "description": "Invoice footer"},
                {"setting_name": "currency_symbol", "setting_value": "$", "description": "Currency symbol"},
                {"setting_name": "currency_code", "setting_value": "USD", "description": "Currency code"},
                {"setting_name": "barcode_prefix", "setting_value": "PRD", "description": "Barcode prefix"},
                {"setting_name": "low_stock_threshold", "setting_value": "5", "description": "Low stock threshold"},
                {"setting_name": "default_tax_rate_id", "setting_value": "", "description": "Default tax rate ID"},
                {"setting_name": "auto_detect_products", "setting_value": "true", "description": "Enable auto product detection"},
                {"setting_name": "auto_create_unknown_products", "setting_value": "false", "description": "Auto create unknown products"},
                {"setting_name": "report_export_path", "setting_value": "reports", "description": "Path to save reports"},
                {"setting_name": "enable_barcode_scanning", "setting_value": "true", "description": "Enable barcode scanning"},
                {"setting_name": "enable_analytics", "setting_value": "true", "description": "Enable analytics dashboard"},
                {"setting_name": "enable_auto_backup", "setting_value": "true", "description": "Enable automatic backups"}
            ]
            
            for setting in default_settings:
                self.data['system_settings'].append(setting)
            
            self._save_data()
    
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256 with salt"""
        salt = "inventory_system_salt"
        return hashlib.sha256((password + salt).encode()).hexdigest()
    
    # System Settings Management
    def get_setting(self, setting_name: str, default: str = None):
        """Get a system setting value"""
        setting = next((s for s in self.data['system_settings'] if s['setting_name'] == setting_name), None)
        return setting['setting_value'] if setting else default
    
    def update_setting(self, setting_name: str, setting_value: str):
        """Update a system setting"""
        setting = next((s for s in self.data['system_settings'] if s['setting_name'] == setting_name), None)
        if setting:
            setting['setting_value'] = setting_value
            self._save_data()
            return True
        return False
    
    def get_all_settings(self):
        """Get all system settings"""
        return self.data['system_settings']
    
    # User Management
    def add_user(self, user_data: dict):
        """Add a new user"""
        try:
            if 'username' not in user_data or 'password' not in user_data:
                return None
                
            # Check if username already exists
            if any(u['username'] == user_data['username'] for u in self.data['users']):
                return None
                
            user_data['id'] = str(uuid.uuid4())
            user_data['password'] = self._hash_password(user_data['password'])
            user_data['created_at'] = datetime.datetime.now().isoformat()
            user_data['is_active'] = user_data.get('is_active', True)
            user_data['failed_login_attempts'] = 0
            user_data['last_login'] = None
            
            self.data['users'].append(user_data)
            self._save_data()
            return user_data['id']
        except Exception as e:
            st.error(f"Error adding user: {e}")
            return None
    
    def get_user(self, username: str):
        """Get user by username"""
        return next((u for u in self.data['users'] if u['username'] == username), None)
    
    def get_user_by_id(self, user_id: str):
        """Get user by ID"""
        return next((u for u in self.data['users'] if u['id'] == user_id), None)
    
    def get_users(self):
        """Get all users"""
        return self.data['users']
    
    def update_user(self, user_id: str, update_data: dict):
        """Update user information"""
        user = next((u for u in self.data['users'] if u['id'] == user_id), None)
        if user:
            # Don't allow updating username
            if 'username' in update_data:
                del update_data['username']
                
            # Handle password update
            if 'password' in update_data:
                update_data['password'] = self._hash_password(update_data['password'])
                
            user.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_user(self, user_id: str):
        """Delete a user"""
        try:
            # Can't delete yourself
            if st.session_state.get('user_id') == user_id:
                return False, "Cannot delete your own account"
                
            self.data['users'] = [u for u in self.data['users'] if u['id'] != user_id]
            self._save_data()
            return True, "User deleted successfully"
        except Exception as e:
            return False, f"Error deleting user: {e}"
    
    # Category Management
    def add_category(self, category_data: dict):
        """Add a new category"""
        try:
            category_data['id'] = str(uuid.uuid4())
            category_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['categories'].append(category_data)
            self._save_data()
            return category_data['id']
        except Exception as e:
            st.error(f"Error adding category: {e}")
            return None
    
    def get_categories(self):
        """Get all categories"""
        return self.data['categories']
    
    def get_category(self, category_id: str):
        """Get a specific category by ID"""
        return next((c for c in self.data['categories'] if c['id'] == category_id), None)
    
    def update_category(self, category_id: str, update_data: dict):
        """Update a category"""
        category = next((c for c in self.data['categories'] if c['id'] == category_id), None)
        if category:
            category.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_category(self, category_id: str):
        """Delete a category"""
        try:
            # Check if category has subcategories
            has_subcategories = any(sc for sc in self.data['subcategories'] if sc['category_id'] == category_id)
            if has_subcategories:
                return False, "Category has subcategories. Delete them first."
            
            self.data['categories'] = [c for c in self.data['categories'] if c['id'] != category_id]
            self._save_data()
            return True, "Category deleted successfully"
        except Exception as e:
            return False, f"Error deleting category: {e}"
    
    # Subcategory Management
    def add_subcategory(self, subcategory_data: dict):
        """Add a new subcategory"""
        try:
            subcategory_data['id'] = str(uuid.uuid4())
            subcategory_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['subcategories'].append(subcategory_data)
            self._save_data()
            return subcategory_data['id']
        except Exception as e:
            st.error(f"Error adding subcategory: {e}")
            return None
    
    def get_subcategories(self, category_id: str = None):
        """Get all subcategories, optionally filtered by category"""
        if category_id:
            return [sc for sc in self.data['subcategories'] if sc['category_id'] == category_id]
        return self.data['subcategories']
    
    def get_subcategory(self, subcategory_id: str):
        """Get a specific subcategory by ID"""
        return next((sc for sc in self.data['subcategories'] if sc['id'] == subcategory_id), None)
    
    def update_subcategory(self, subcategory_id: str, update_data: dict):
        """Update a subcategory"""
        subcategory = next((sc for sc in self.data['subcategories'] if sc['id'] == subcategory_id), None)
        if subcategory:
            subcategory.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_subcategory(self, subcategory_id: str):
        """Delete a subcategory"""
        try:
            # Check if subcategory has products
            has_products = any(p for p in self.data['inventory'] if p.get('subcategory_id') == subcategory_id)
            if has_products:
                return False, "Subcategory has products. Reassign them first."
            
            self.data['subcategories'] = [sc for sc in self.data['subcategories'] if sc['id'] != subcategory_id]
            self._save_data()
            return True, "Subcategory deleted successfully"
        except Exception as e:
            return False, f"Error deleting subcategory: {e}"
    
    # Brand Management
    def add_brand(self, brand_data: dict):
        """Add a new brand"""
        try:
            brand_data['id'] = str(uuid.uuid4())
            brand_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['brands'].append(brand_data)
            self._save_data()
            return brand_data['id']
        except Exception as e:
            st.error(f"Error adding brand: {e}")
            return None
    
    def get_brands(self):
        """Get all brands"""
        return self.data['brands']
    
    def get_brand(self, brand_id: str):
        """Get a specific brand by ID"""
        return next((b for b in self.data['brands'] if b['id'] == brand_id), None)
    
    def update_brand(self, brand_id: str, update_data: dict):
        """Update a brand"""
        brand = next((b for b in self.data['brands'] if b['id'] == brand_id), None)
        if brand:
            brand.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_brand(self, brand_id: str):
        """Delete a brand"""
        try:
            # Check if brand has products
            has_products = any(p for p in self.data['inventory'] if p.get('brand_id') == brand_id)
            if has_products:
                return False, "Brand has products. Reassign them first."
            
            self.data['brands'] = [b for b in self.data['brands'] if b['id'] != brand_id]
            self._save_data()
            return True, "Brand deleted successfully"
        except Exception as e:
            return False, f"Error deleting brand: {e}"
    
    # Location Management
    def add_location(self, location_data: dict):
        """Add a new location"""
        try:
            location_data['id'] = str(uuid.uuid4())
            location_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['locations'].append(location_data)
            self._save_data()
            return location_data['id']
        except Exception as e:
            st.error(f"Error adding location: {e}")
            return None
    
    def get_locations(self):
        """Get all locations"""
        return self.data['locations']
    
    def get_location(self, location_id: str):
        """Get a specific location by ID"""
        return next((l for l in self.data['locations'] if l['id'] == location_id), None)
    
    def update_location(self, location_id: str, update_data: dict):
        """Update a location"""
        location = next((l for l in self.data['locations'] if l['id'] == location_id), None)
        if location:
            location.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_location(self, location_id: str):
        """Delete a location"""
        try:
            # Check if location has products
            has_products = any(p for p in self.data['inventory'] if p.get('location_id') == location_id)
            if has_products:
                return False, "Location has products. Reassign them first."
            
            self.data['locations'] = [l for l in self.data['locations'] if l['id'] != location_id]
            self._save_data()
            return True, "Location deleted successfully"
        except Exception as e:
            return False, f"Error deleting location: {e}"
    
    # Tax Rate Management
    def add_tax_rate(self, tax_rate_data: dict):
        """Add a new tax rate"""
        try:
            tax_rate_data['id'] = str(uuid.uuid4())
            self.data['tax_rates'].append(tax_rate_data)
            
            # If this is set as default, unset any other default
            if tax_rate_data.get('is_default', False):
                for tr in self.data['tax_rates']:
                    if tr['id'] != tax_rate_data['id']:
                        tr['is_default'] = False
                self.update_setting('default_tax_rate_id', tax_rate_data['id'])
            
            self._save_data()
            return tax_rate_data['id']
        except Exception as e:
            st.error(f"Error adding tax rate: {e}")
            return None
    
    def get_tax_rates(self):
        """Get all tax rates"""
        return self.data['tax_rates']
    
    def get_tax_rate(self, tax_rate_id: str):
        """Get a specific tax rate by ID"""
        return next((tr for tr in self.data['tax_rates'] if tr['id'] == tax_rate_id), None)
    
    def update_tax_rate(self, tax_rate_id: str, update_data: dict):
        """Update a tax rate"""
        tax_rate = next((tr for tr in self.data['tax_rates'] if tr['id'] == tax_rate_id), None)
        if tax_rate:
            # If setting as default, unset any other default
            if update_data.get('is_default', False):
                for tr in self.data['tax_rates']:
                    if tr['id'] != tax_rate_id:
                        tr['is_default'] = False
                self.update_setting('default_tax_rate_id', tax_rate_id)
            
            tax_rate.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_tax_rate(self, tax_rate_id: str):
        """Delete a tax rate"""
        try:
            # Check if this is the default tax rate
            default_tax_id = self.get_setting('default_tax_rate_id')
            if tax_rate_id == default_tax_id:
                return False, "Cannot delete the default tax rate. Set another as default first."
            
            self.data['tax_rates'] = [tr for tr in self.data['tax_rates'] if tr['id'] != tax_rate_id]
            self._save_data()
            return True, "Tax rate deleted successfully"
        except Exception as e:
            return False, f"Error deleting tax rate: {e}"
    
    
    # Supplier Management
    def add_supplier(self, supplier_data: dict):
        """Add a new supplier"""
        try:
            supplier_data['id'] = str(uuid.uuid4())
            supplier_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['suppliers'].append(supplier_data)
            self._save_data()
            return supplier_data['id']
        except Exception as e:
            st.error(f"Error adding supplier: {e}")
            return None
    
    def get_suppliers(self):
        """Get all suppliers"""
        return self.data['suppliers']
    
    def get_supplier(self, supplier_id: str):
        """Get a specific supplier by ID"""
        return next((s for s in self.data['suppliers'] if s['id'] == supplier_id), None)
    
    def update_supplier(self, supplier_id: str, update_data: dict):
        """Update a supplier"""
        supplier = next((s for s in self.data['suppliers'] if s['id'] == supplier_id), None)
        if supplier:
            supplier.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_supplier(self, supplier_id: str):
        """Delete a supplier"""
        try:
            # Check if supplier has products
            has_products = any(p for p in self.data['inventory'] if p.get('supplier_id') == supplier_id)
            if has_products:
                return False, "Supplier has products. Reassign them first."
            
            self.data['suppliers'] = [s for s in self.data['suppliers'] if s['id'] != supplier_id]
            self._save_data()
            return True, "Supplier deleted successfully"
        except Exception as e:
            return False, f"Error deleting supplier: {e}"
    
    # Customer Management
    def add_customer(self, customer_data: dict):
        """Add a new customer"""
        try:
            customer_data['id'] = str(uuid.uuid4())
            customer_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['customers'].append(customer_data)
            self._save_data()
            return customer_data['id']
        except Exception as e:
            st.error(f"Error adding customer: {e}")
            return None
    
    def get_customers(self):
        """Get all customers"""
        return self.data['customers']
    
    def get_customer(self, customer_id: str):
        """Get a specific customer by ID"""
        return next((c for c in self.data['customers'] if c['id'] == customer_id), None)
    
    def update_customer(self, customer_id: str, update_data: dict):
        """Update a customer"""
        customer = next((c for c in self.data['customers'] if c['id'] == customer_id), None)
        if customer:
            customer.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_customer(self, customer_id: str):
        """Delete a customer"""
        try:
            # Check if customer has invoices
            has_invoices = any(i for i in self.data['invoices'] if i.get('customer_id') == customer_id)
            if has_invoices:
                return False, "Customer has invoices. Cannot delete."
            
            self.data['customers'] = [c for c in self.data['customers'] if c['id'] != customer_id]
            self._save_data()
            return True, "Customer deleted successfully"
        except Exception as e:
            return False, f"Error deleting customer: {e}"
    
    # Invoice Management
    def add_invoice(self, invoice_data: dict):
        """Add a new invoice"""
        try:
            invoice_data['id'] = str(uuid.uuid4())
            invoice_data['created_at'] = datetime.datetime.now().isoformat()
            
            # Generate invoice number
            prefix = self.get_setting('invoice_prefix', 'INV')
            invoice_data['invoice_number'] = f"{prefix}-{datetime.datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
            
            self.data['invoices'].append(invoice_data)
            self._save_data()
            return invoice_data['id']
        except Exception as e:
            st.error(f"Error adding invoice: {e}")
            return None
    
    def get_invoices(self):
        """Get all invoices"""
        return self.data['invoices']
    
    def get_invoice(self, invoice_id: str):
        """Get a specific invoice by ID"""
        return next((i for i in self.data['invoices'] if i['id'] == invoice_id), None)
    
    def get_invoice_by_number(self, invoice_number: str):
        """Get invoice by invoice number"""
        return next((i for i in self.data['invoices'] if i['invoice_number'] == invoice_number), None)
    
    def update_invoice(self, invoice_id: str, update_data: dict):
        """Update an invoice"""
        invoice = next((i for i in self.data['invoices'] if i['id'] == invoice_id), None)
        if invoice:
            invoice.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_invoice(self, invoice_id: str):
        """Delete an invoice"""
        try:
            # First delete all invoice items
            self.data['invoice_items'] = [ii for ii in self.data['invoice_items'] if ii['invoice_id'] != invoice_id]
            
            # Then delete the invoice
            self.data['invoices'] = [i for i in self.data['invoices'] if i['id'] != invoice_id]
            self._save_data()
            return True, "Invoice deleted successfully"
        except Exception as e:
            return False, f"Error deleting invoice: {e}"
    
    def get_invoice_details(self, invoice_id: str):
        """Get complete invoice details including items"""
        invoice = self.get_invoice(invoice_id)
        if not invoice:
            return None
            
        items = [ii for ii in self.data['invoice_items'] if ii['invoice_id'] == invoice_id]
        
        # Calculate totals
        subtotal = sum(item['unit_price'] * item['quantity'] for item in items)
        discount = sum(item.get('discount', 0) for item in items)
        tax = invoice.get('tax_amount', 0)
        shipping = invoice.get('shipping_cost', 0)
        total = subtotal - discount + tax + shipping
        
        # Get customer details
        customer = self.get_customer(invoice['customer_id']) if invoice.get('customer_id') else None
        
        return {
            'header': {
                'invoice_number': invoice['invoice_number'],
                'date': invoice.get('date', invoice['created_at']),
                'due_date': invoice.get('due_date'),
                'status': invoice.get('status', 'draft'),
                'payment_terms': invoice.get('payment_terms', 'Due on receipt'),
                'notes': invoice.get('notes', ''),
                'customer_id': invoice.get('customer_id'),
                'customer_name': customer['name'] if customer else 'Walk-in Customer',
                'customer_email': customer.get('email') if customer else '',
                'subtotal': subtotal,
                'discount': discount,
                'tax': tax,
                'shipping_cost': shipping,
                'total': total
            },
            'items': items
        }
    
    def add_invoice_item(self, item_data: dict):
        """Add an item to an invoice"""
        try:
            item_data['id'] = str(uuid.uuid4())
            self.data['invoice_items'].append(item_data)
            self._save_data()
            return item_data['id']
        except Exception as e:
            st.error(f"Error adding invoice item: {e}")
            return None
    
    def get_invoice_items(self, invoice_id: str):
        """Get all items for an invoice"""
        return [ii for ii in self.data['invoice_items'] if ii['invoice_id'] == invoice_id]
    
    def update_invoice_item(self, item_id: str, update_data: dict):
        """Update an invoice item"""
        item = next((ii for ii in self.data['invoice_items'] if ii['id'] == item_id), None)
        if item:
            item.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_invoice_item(self, item_id: str):
        """Delete an invoice item"""
        try:
            self.data['invoice_items'] = [ii for ii in self.data['invoice_items'] if ii['id'] != item_id]
            self._save_data()
            return True, "Invoice item deleted successfully"
        except Exception as e:
            return False, f"Error deleting invoice item: {e}"
    
    # Transaction Management
    def add_transaction(self, transaction_data: dict):
        """Add a new transaction"""
        try:
            transaction_data['id'] = str(uuid.uuid4())
            transaction_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['transactions'].append(transaction_data)
            self._save_data()
            return transaction_data['id']
        except Exception as e:
            st.error(f"Error adding transaction: {e}")
            return None
    
    def get_transactions(self):
        """Get all transactions"""
        return self.data['transactions']
    
    def get_transaction(self, transaction_id: str):
        """Get a specific transaction by ID"""
        return next((t for t in self.data['transactions'] if t['id'] == transaction_id), None)
    
    def update_transaction(self, transaction_id: str, update_data: dict):
        """Update a transaction"""
        transaction = next((t for t in self.data['transactions'] if t['id'] == transaction_id), None)
        if transaction:
            transaction.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_transaction(self, transaction_id: str):
        """Delete a transaction"""
        try:
            self.data['transactions'] = [t for t in self.data['transactions'] if t['id'] != transaction_id]
            self._save_data()
            return True, "Transaction deleted successfully"
        except Exception as e:
            return False, f"Error deleting transaction: {e}"
    
    # Payment Management
    def add_payment(self, payment_data: dict):
        """Add a new payment"""
        try:
            payment_data['id'] = str(uuid.uuid4())
            payment_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['payments'].append(payment_data)
            self._save_data()
            return payment_data['id']
        except Exception as e:
            st.error(f"Error adding payment: {e}")
            return None
    
    def get_payments(self):
        """Get all payments"""
        return self.data['payments']
    
    def get_payment(self, payment_id: str):
        """Get a specific payment by ID"""
        return next((p for p in self.data['payments'] if p['id'] == payment_id), None)
    
    def update_payment(self, payment_id: str, update_data: dict):
        """Update a payment"""
        payment = next((p for p in self.data['payments'] if p['id'] == payment_id), None)
        if payment:
            payment.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_payment(self, payment_id: str):
        """Delete a payment"""
        try:
            self.data['payments'] = [p for p in self.data['payments'] if p['id'] != payment_id]
            self._save_data()
            return True, "Payment deleted successfully"
        except Exception as e:
            return False, f"Error deleting payment: {e}"
    
    # Bank Account Management
    def add_bank_account(self, account_data: dict):
        """Add a new bank account"""
        try:
            account_data['id'] = str(uuid.uuid4())
            account_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['bank_accounts'].append(account_data)
            self._save_data()
            return account_data['id']
        except Exception as e:
            st.error(f"Error adding bank account: {e}")
            return None
    
    def get_bank_accounts(self):
        """Get all bank accounts"""
        return self.data['bank_accounts']
    
    def get_bank_account(self, account_id: str):
        """Get a specific bank account by ID"""
        return next((a for a in self.data['bank_accounts'] if a['id'] == account_id), None)
    
    def update_bank_account(self, account_id: str, update_data: dict):
        """Update a bank account"""
        account = next((a for a in self.data['bank_accounts'] if a['id'] == account_id), None)
        if account:
            account.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_bank_account(self, account_id: str):
        """Delete a bank account"""
        try:
            # Check if account has transactions
            has_transactions = any(t for t in self.data['transactions'] if t.get('account_id') == account_id)
            if has_transactions:
                return False, "Bank account has transactions. Cannot delete."
            
            self.data['bank_accounts'] = [a for a in self.data['bank_accounts'] if a['id'] != account_id]
            self._save_data()
            return True, "Bank account deleted successfully"
        except Exception as e:
            return False, f"Error deleting bank account: {e}"
    
    # Unknown Product Management
    def add_unknown_product(self, product_data: dict):
        """Add an unknown product detected from scanning"""
        try:
            product_data['id'] = str(uuid.uuid4())
            product_data['detected_at'] = datetime.datetime.now().isoformat()
            product_data['status'] = 'pending'  # pending, processed, ignored
            self.data['unknown_products'].append(product_data)
            self._save_data()
            return product_data['id']
        except Exception as e:
            st.error(f"Error adding unknown product: {e}")
            return None
    
    def get_unknown_products(self, status: str = None):
        """Get unknown products, optionally filtered by status"""
        if status:
            return [up for up in self.data['unknown_products'] if up['status'] == status]
        return self.data['unknown_products']
    
    def update_unknown_product(self, product_id: str, update_data: dict):
        """Update an unknown product"""
        product = next((up for up in self.data['unknown_products'] if up['id'] == product_id), None)
        if product:
            product.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_unknown_product(self, product_id: str):
        """Delete an unknown product"""
        try:
            self.data['unknown_products'] = [up for up in self.data['unknown_products'] if up['id'] != product_id]
            self._save_data()
            return True
        except Exception as e:
            st.error(f"Error deleting unknown product: {e}")
            return False
    
    # Audit Log Management
    def log_audit(self, user_id: str, action: str, details: str = None):
        """Add an audit log entry"""
        try:
            log_entry = {
                'id': str(uuid.uuid4()),
                'user_id': user_id,
                'action': action,
                'details': details or '',
                'timestamp': datetime.datetime.now().isoformat()
            }
            self.data['audit_log'].append(log_entry)
            self._save_data()
            return log_entry['id']
        except Exception as e:
            st.error(f"Error logging audit: {e}")
            return None
    
    def get_audit_logs(self, user_id: str = None, action: str = None):
        """Get audit logs, optionally filtered by user or action"""
        logs = self.data['audit_log']
        if user_id:
            logs = [l for l in logs if l['user_id'] == user_id]
        if action:
            logs = [l for l in logs if l['action'] == action]
        return logs
    
    # Backup Management
    def create_backup(self, backup_name: str = None, backup_data: str = None):

      try:
         backup_name = backup_name or f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
         backup_data = backup_data or json.dumps(self.data)  # Use provided data or current database
         
         backup_entry = {
            'id': str(uuid.uuid4()),
            'name': backup_name,
            'created_at': datetime.datetime.now().isoformat(),
            'data': backup_data
         }
        
         self.data['backups'].append(backup_entry)
         self._save_data()
         return backup_entry['id']
      except Exception as e:
        st.error(f"Error creating backup: {e}")
        return None
    
    def restore_backup(self, backup_id: str):
      """Restore database from a backup"""
      try:
         backup = next((b for b in self.data['backups'] if b['id'] == backup_id), None)
         if not backup:
             return False, "Backup not found"
        
         # Parse the backup data
         backup_data = json.loads(backup['data'])
        
         # Restore each section from the backup
         if 'settings' in backup_data:
            self.data['system_settings'] = backup_data['settings']
        
         if 'users' in backup_data:
            self.data['users'] = backup_data['users']
        
         if 'products' in backup_data:
            self.data['inventory'] = backup_data['products']
         
         if 'customers' in backup_data:
            self.data['customers'] = backup_data['customers']
        
         if 'transactions' in backup_data:
            self.data['transactions'] = backup_data['transactions']
        
         if 'tax_rates' in backup_data:
            self.data['tax_rates'] = backup_data['tax_rates']
        
         # Save the restored data
         self._save_data()
         return True, "Backup restored successfully"
      except Exception as e:
        return False, f"Error restoring backup: {e}"
    
    
    def delete_backup(self, backup_id: str):
        """Delete a backup"""
        try:
            self.data['backups'] = [b for b in self.data['backups'] if b['id'] != backup_id]
            self._save_data()
            return True, "Backup deleted successfully"
        except Exception as e:
            return False, f"Error deleting backup: {e}"
    
    # Report Management
    def add_report(self, report_data: dict):
        """Add a new report"""
        try:
            report_data['id'] = str(uuid.uuid4())
            report_data['created_at'] = datetime.datetime.now().isoformat()
            self.data['reports'].append(report_data)
            self._save_data()
            return report_data['id']
        except Exception as e:
            st.error(f"Error adding report: {e}")
            return None
    
    def get_reports(self):
        """Get all reports"""
        return self.data['reports']
    
    def get_report(self, report_id: str):
        """Get a specific report by ID"""
        return next((r for r in self.data['reports'] if r['id'] == report_id), None)
    
    def update_report(self, report_id: str, update_data: dict):
        """Update a report"""
        report = next((r for r in self.data['reports'] if r['id'] == report_id), None)
        if report:
            report.update(update_data)
            self._save_data()
            return True
        return False
    
    def delete_report(self, report_id: str):
        """Delete a report"""
        try:
            self.data['reports'] = [r for r in self.data['reports'] if r['id'] != report_id]
            self._save_data()
            return True, "Report deleted successfully"
        except Exception as e:
            return False, f"Error deleting report: {e}"

# Initialize database
db = JSONDatabase()

# =============================================
# Authentication & User Management
# =============================================

def login(username: str, password: str) -> bool:
    """Authenticate user with enhanced security checks"""
    try:
        user = db.get_user(username)
        if not user:
            return False
        
        # Check if account is locked
        if user.get('failed_login_attempts', 0) >= 5:
            last_failed = datetime.datetime.fromisoformat(user.get('last_failed_login', '2000-01-01'))
            if (datetime.datetime.now() - last_failed).seconds < 3600:  # 1 hour lock
                st.error("Account locked due to too many failed attempts. Try again later.")
                return False
        
        # Check credentials
        if user['password'] == db._hash_password(password) and user.get('is_active', True):
            st.session_state.authenticated = True
            st.session_state.current_user = user['username']
            st.session_state.current_role = user['role']
            st.session_state.user_id = user['id']
            st.session_state.user_email = user.get('email', '')
            
            # Reset failed attempts
            db.update_user(user['id'], {
                'failed_login_attempts': 0,
                'last_login': datetime.datetime.now().isoformat()
            })
            
            # Log the login
            db.log_audit(user['id'], "login")
            return True
        else:
            # Increment failed attempts
            db.update_user(user['id'], {
                'failed_login_attempts': user.get('failed_login_attempts', 0) + 1,
                'last_failed_login': datetime.datetime.now().isoformat()
            })
            return False
    except Exception as e:
        st.error(f"Login error: {e}")
    return False

def login_form():
    """Enhanced login form with security features"""
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        with st.container(border=True):
            st.subheader("Inventory System Login")
            
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            
            if st.button("Login", use_container_width=True):
                if login(username, password):
                    st.success("Login successful")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            
            if st.button("Forgot Password?", use_container_width=True):
                st.info("Please contact your system administrator to reset your password")

def logout():
    """Log out the current user with audit logging"""
    if st.session_state.authenticated:
        db.log_audit(st.session_state.user_id, "logout")
    st.session_state.authenticated = False
    st.session_state.current_user = None
    st.session_state.current_role = None
    st.session_state.user_id = None
    st.session_state.user_email = None

def check_permission(required_permission: str) -> bool:
    """Check if current user has required permission with role hierarchy"""
    if not st.session_state.authenticated:
        return False
    
    # Admin has all permissions
    if st.session_state.current_role == "Admin":
        return True
    
    # Default permissions for roles
    role_permissions = {
        "Manager": [
            "view_inventory", "edit_inventory", "view_reports", 
            "create_invoice", "manage_customers", "view_suppliers",
            "manage_categories", "view_settings", "scan_products",
            "view_analytics", "generate_reports"
        ],
        "Sales": [
            "view_inventory", "create_invoice", "view_customers",
            "view_sales_reports", "process_payments", "scan_products"
        ],
        "Warehouse": [
            "view_inventory", "edit_inventory", "receive_stock",
            "manage_locations", "view_suppliers", "scan_products"
        ]
    }
    
    return required_permission in role_permissions.get(st.session_state.current_role, [])

# =============================================
# Barcode & Image Processing with Auto-Detection
# =============================================

def process_barcode_image(image):
    """Process an image to detect barcodes with enhanced detection"""
    try:
        # Convert PIL Image to OpenCV format
        img = np.array(image.convert('RGB'))
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        
        # Apply image enhancements
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY, 11, 2)
        gray = cv2.medianBlur(gray, 3)
        
        # Try different barcode types
        detected_barcodes = decode(gray)
        
        if detected_barcodes:
            barcodes = []
            for barcode in detected_barcodes:
                try:
                    barcode_data = barcode.data.decode("utf-8")
                    barcode_type = barcode.type
                    barcodes.append({
                        'data': barcode_data,
                        'type': barcode_type,
                        'polygon': barcode.polygon
                    })
                except:
                    continue
            return barcodes if barcodes else None
        return None
    except Exception as e:
        st.error(f"Barcode processing error: {e}")
        return None

def generate_barcode(product_id: str, product_name: str) -> str:
    """Generate a unique barcode for a product"""
    try:
        prefix = db.get_setting('barcode_prefix', 'PRD')
        timestamp = int(time.time())
        hash_part = hashlib.md5(f"{product_id}{product_name}{timestamp}".encode()).hexdigest()[:8].upper()
        return f"{prefix}-{product_id[:6]}-{hash_part}"
    except Exception as e:
        st.error(f"Barcode generation error: {e}")
        return None

def extract_product_info_from_barcode(barcode_data: str) -> dict:
    """Attempt to extract product information from barcode data"""
    try:
        # Simple pattern matching for demo purposes
        patterns = {
            r'^PRD-': {'type': 'internal'},
            r'^ABC-\d{4}': {'brand': 'ABC Corp', 'type': 'electronics'},
            r'^XYZ-[A-Z]{3}': {'brand': 'XYZ Brands', 'type': 'clothing'}
        }
        
        info = {}
        
        for pattern, data in patterns.items():
            if re.match(pattern, barcode_data):
                info.update(data)
                break
        
        return info if info else None
    except Exception as e:
        st.error(f"Error extracting product info: {e}")
        return None

# =============================================
# Enhanced Barcode Scanner with Auto-Detection
# =============================================


def barcode_scanner():
    """Enhanced barcode scanning interface with auto-detection and better image processing"""
    if not check_permission("scan_products"):
        st.warning("You don't have permission to access this section")
        return
    
    st.subheader("📷 Barcode Scanner")
    
    # Check if barcode scanning is enabled
    if db.get_setting('enable_barcode_scanning', 'true').lower() != 'true':
        st.warning("Barcode scanning is currently disabled in system settings")
        return
    
    # Camera input and file upload
    scan_option = st.radio("Scan Option", ["Use Camera", "Upload Image"], horizontal=True, key="scan_option")
    
    if scan_option == "Use Camera":
        img_file = st.camera_input("Scan barcode", key="barcode_scanner_camera")
    else:
        img_file = st.file_uploader("Upload barcode image", type=["jpg", "jpeg", "png"], key="barcode_upload")
    
    if img_file:
        try:
            image = Image.open(img_file)
            
            # Display the original image
            st.image(image, caption="Original Image", use_column_width=True)
            
            # Process image
            with st.spinner("Processing barcode..."):
                # Convert to numpy array and grayscale
                img = np.array(image.convert('RGB'))
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                
                # Apply adaptive thresholding
                gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                           cv2.THRESH_BINARY, 11, 2)
                
                # Apply morphological operations to clean up the image
                kernel = np.ones((3, 3), np.uint8)
                gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
                
                # Try decoding with both processed and original images
                detected_barcodes = []
                
                # First try with processed grayscale image
                barcodes = decode(gray)
                if barcodes:
                    detected_barcodes.extend(barcodes)
                
                # If nothing found, try with original color image
                if not detected_barcodes:
                    barcodes = decode(img)
                    if barcodes:
                        detected_barcodes.extend(barcodes)
            
            if detected_barcodes:
                st.success(f"✅ {len(detected_barcodes)} barcode(s) detected!")
                
                for barcode in detected_barcodes:
                    try:
                        barcode_data = barcode.data.decode("utf-8")
                        barcode_type = barcode.type
                        
                        # Draw bounding box on the image
                        img_with_boxes = img.copy()
                        points = barcode.polygon
                        if len(points) > 4: 
                            hull = cv2.convexHull(np.array([point for point in points], dtype=np.int32))
                            cv2.polylines(img_with_boxes, [hull], True, (0, 255, 0), 3)
                        else:
                            cv2.polylines(img_with_boxes, [np.array(points, dtype=np.int32)], True, (0, 255, 0), 3)
                        
                        # Display processed image with bounding box
                        st.image(img_with_boxes, caption=f"Detected {barcode_type} Barcode", use_column_width=True)
                        
                        st.write(f"**Type:** {barcode_type}")
                        st.write(f"**Data:** `{barcode_data}`")
                        
                        # Look up item in inventory
                        item = db.get_inventory_item_by_barcode(barcode_data)
                        
                        if item:
                            st.success("🎉 Matching inventory item found!")
                            display_product_details(item)
                            
                            # Quick update form
                            with st.expander("Quick Update Item"):
                                quick_update_form(item)
                        else:
                            st.warning("⚠️ No matching inventory item found for this barcode")
                            handle_unknown_product(barcode_data, barcode_type)
                            
                    except Exception as e:
                        st.error(f"Error processing barcode: {str(e)}")
                        continue
            else:
                st.warning("⚠️ No barcode detected in the image")
                # Show processed image for debugging
                st.image(gray, caption="Processed Image (Grayscale)", use_column_width=True)
                
        except Exception as e:
            st.error(f"Error processing image: {str(e)}")

def display_product_details(item):
    """Display product details in a formatted way"""
    col1, col2 = st.columns([1, 2])
    with col1:
        if item.get('image_path') and os.path.exists(item['image_path']):
            st.image(item['image_path'], caption=item['name'], width=150)
        else:
            st.info("No product image available")
    
    with col2:
        st.write(f"**Product:** {item['name']}")
        if item.get('brand_id'):
            brand = db.get_brand(item['brand_id'])
            st.write(f"**Brand:** {brand['name'] if brand else 'N/A'}")
        st.write(f"**Price:** ${item['price']:.2f}")
        st.write(f"**Stock:** {item['quantity']} units")
        
        if item.get('category_id'):
            category = db.get_category(item['category_id'])
            st.write(f"**Category:** {category['name'] if category else 'N/A'}")
        
        if item.get('subcategory_id'):
            subcategory = db.get_subcategory(item['subcategory_id'])
            st.write(f"**Subcategory:** {subcategory['name'] if subcategory else 'N/A'}")

def quick_update_form(item):
    """Form for quick updates to inventory items"""
    with st.form(f"quick_update_form_{item['id']}"):
        st.write("### Update Inventory Item")
        
        col1, col2 = st.columns(2)
        with col1:
            new_quantity = st.number_input(
                "Quantity", 
                min_value=0,
                value=item['quantity'],
                key=f"qty_{item['id']}"
            )
            new_price = st.number_input(
                "Price", 
                min_value=0.0,
                value=float(item['price']),
                step=0.01,
                key=f"price_{item['id']}"
            )
        with col2:
            locations = db.get_locations()
            current_location = item.get('location_id', '')
            location_index = next((i for i, l in enumerate(locations) if l['id'] == current_location), 0)
            new_location = st.selectbox(
                "Location",
                options=[l['id'] for l in locations],
                format_func=lambda x: next(l['name'] for l in locations if l['id'] == x),
                index=location_index,
                key=f"loc_{item['id']}"
            )
            new_min_stock = st.number_input(
                "Min Stock",
                min_value=0,
                value=item.get('min_stock', 5),
                key=f"min_{item['id']}"
            )
        
        if st.form_submit_button("Update Item"):
            update_data = {
                'quantity': new_quantity,
                'price': new_price,
                'location_id': new_location,
                'min_stock': new_min_stock
            }
            
            if db.update_inventory_item(item['id'], update_data):
                st.success("Item updated successfully!")
                time.sleep(1)
                st.rerun()

def handle_unknown_product(barcode_data, barcode_type):
    """Handle unknown barcode products with box scanning and auto-fill"""
    # Check if auto-create unknown products is enabled
    auto_create = db.get_setting('auto_create_unknown_products', 'false').lower() == 'true'
    
    if auto_create:
        # Add to unknown products list
        unknown_product = {
            'barcode': barcode_data,
            'barcode_type': barcode_type,
            'detected_at': datetime.datetime.now().isoformat(),
            'status': 'pending'
        }
        
        db.add_unknown_product(unknown_product)
        st.success("Unknown product added to pending list for review")
    else:
        # Main container for the product creation form
        with st.container():
            st.write("## Add New Product from Barcode")
            
            # Step 1: Box Scanning Section
            with st.expander("📦 Step 1: Scan Product Box", expanded=True):
                st.write("Take a clear photo of the product box to auto-fill information")
                
                # Camera input for box scanning
                box_scan = st.camera_input("Position the product box in frame and take photo", 
                                         key=f"box_scan_{barcode_data}")
                
                if box_scan:
                    try:
                        # Display the scanned box image
                        box_image = Image.open(box_scan)
                        st.image(box_image, caption="Scanned Product Box", use_column_width=True)
                        
                        # Process the image to extract text (simulated here - replace with actual OCR)
                        with st.spinner("Extracting product information..."):
                            # This is where you would integrate with an actual OCR service
                            # For demonstration, we'll simulate extracted data
                            
                            # Simulate OCR results based on barcode pattern
                            if barcode_data.startswith("ABC"):
                                box_data = {
                                    'name': f"Premium Product {barcode_data[-4:]}",
                                    'brand': "ABC Brand",
                                    'category': "Electronics",
                                    'description': f"High-quality electronic product with model number {barcode_data[-4:]}"
                                }
                            elif barcode_data.startswith("XYZ"):
                                box_data = {
                                    'name': f"Basic Product {barcode_data[-4:]}",
                                    'brand': "XYZ Brands",
                                    'category': "Home Goods",
                                    'description': f"Standard home good product {barcode_data[-4:]}"
                                }
                            else:
                                box_data = {
                                    'name': f"Generic Product {barcode_data[-6:]}",
                                    'brand': "Generic Brand",
                                    'category': "General Merchandise",
                                    'description': f"Product with barcode {barcode_data}"
                                }
                            
                            st.success("✅ Product information extracted from box!")
                            
                            # Store the extracted data in session state
                            st.session_state.box_data = box_data
                            st.session_state.box_scan_complete = True
                    
                    except Exception as e:
                        st.error(f"Error processing box image: {str(e)}")
                        st.session_state.box_scan_complete = False
            
            # Step 2: Product Information Form with auto-fill
            with st.expander("📝 Step 2: Product Details", expanded=True):
                # Initialize form data
                form_data = {
                    'name': '',
                    'description': '',
                    'brand_id': None,
                    'category_id': None,
                    'price': 0.0,
                    'quantity': 0
                }
                
                # Get available brands and categories
                brands = db.get_brands()
                categories = db.get_categories()
                
                # Auto-fill from box scan if available
                if 'box_data' in st.session_state and st.session_state.box_scan_complete:
                    box_data = st.session_state.box_data
                    
                    # Find matching brand
                    brand_match = next((b for b in brands if box_data['brand'].lower() in b['name'].lower()), None)
                    if brand_match:
                        form_data['brand_id'] = brand_match['id']
                    
                    # Find matching category
                    category_match = next((c for c in categories if box_data['category'].lower() in c['name'].lower()), None)
                    if category_match:
                        form_data['category_id'] = category_match['id']
                    
                    form_data.update({
                        'name': box_data.get('name', ''),
                        'description': box_data.get('description', '')
                    })
                
                # Product creation form
                with st.form(f"product_form_{barcode_data}"):
                    # Name and Description
                    form_data['name'] = st.text_input("Product Name*", 
                                                     value=form_data['name'],
                                                     help="Official product name from packaging")
                    
                    form_data['description'] = st.text_area("Description", 
                                                          value=form_data['description'],
                                                          help="Product description from packaging")
                    
                    # Brand and Category selection
                    col1, col2 = st.columns(2)
                    with col1:
                        # Brand dropdown with auto-selection
                        brand_options = [b['id'] for b in brands]
                        brand_names = [b['name'] for b in brands]
                        brand_index = brand_options.index(form_data['brand_id']) if form_data['brand_id'] else 0
                        
                        form_data['brand_id'] = st.selectbox(
                            "Brand*",
                            options=brand_options,
                            format_func=lambda x: next(b['name'] for b in brands if b['id'] == x),
                            index=brand_index
                        )
                        
                        # Price input
                        form_data['price'] = st.number_input("Price*", 
                                                           min_value=0.0, 
                                                           step=0.01,
                                                           value=form_data['price'],
                                                           help="Retail price from packaging")
                    
                    with col2:
                        # Category dropdown with auto-selection
                        category_options = [c['id'] for c in categories]
                        category_names = [c['name'] for c in categories]
                        category_index = category_options.index(form_data['category_id']) if form_data['category_id'] else 0
                        
                        form_data['category_id'] = st.selectbox(
                            "Category*",
                            options=category_options,
                            format_func=lambda x: next(c['name'] for c in categories if c['id'] == x),
                            index=category_index
                        )
                        
                        # Quantity input
                        form_data['quantity'] = st.number_input("Initial Quantity", 
                                                              min_value=0, 
                                                              value=form_data['quantity'],
                                                              step=1)
                    
                    # Hidden barcode field
                    barcode_field = st.text_input("Barcode", value=barcode_data, disabled=True)
                    
                    # Image upload
                    image_file = st.file_uploader("Upload Product Image", 
                                                type=["jpg", "jpeg", "png"],
                                                help="Take or upload a clear photo of the product")
                    
                    # Form submission
                    if st.form_submit_button("Add Product to Inventory"):
                        if not form_data['name'] or not form_data['price'] or not form_data['category_id']:
                            st.error("Please fill in all required fields (marked with *)")
                        else:
                            # Prepare item data for database
                            item_data = {
                                'name': form_data['name'],
                                'description': form_data['description'],
                                'price': form_data['price'],
                                'quantity': form_data['quantity'],
                                'barcode': barcode_field,
                                'category_id': form_data['category_id'],
                                'brand_id': form_data['brand_id']
                            }
                            
                            # Add to database
                            if db.add_inventory_item(item_data):
                                # Handle image upload if provided
                                if image_file:
                                    os.makedirs("uploads/products", exist_ok=True)
                                    file_ext = os.path.splitext(image_file.name)[1]
                                    image_filename = f"product_{int(time.time())}{file_ext}"
                                    image_path = os.path.join("uploads/products", image_filename)
                                    
                                    with open(image_path, "wb") as f:
                                        f.write(image_file.getbuffer())
                                    
                                    # Update item with image path
                                    db.update_inventory_item(item_data['id'], {'image_path': image_path})
                                
                                st.success("Product added successfully!")
                                time.sleep(1)
                                
                                # Clear session state
                                if 'box_data' in st.session_state:
                                    del st.session_state.box_data
                                if 'box_scan_complete' in st.session_state:
                                    del st.session_state.box_scan_complete
                                
                                st.rerun()
def extract_product_info_from_barcode(barcode_data):
    """Attempt to extract product information from barcode data"""
    try:
        # Simple pattern matching for demo purposes
        patterns = {
            r'^PRD-': {'type': 'internal'},
            r'^ABC-\d{4}': {'brand': 'ABC Corp', 'type': 'electronics'},
            r'^XYZ-[A-Z]{3}': {'brand': 'XYZ Brands', 'type': 'clothing'}
        }
        
        info = {}
        
        for pattern, data in patterns.items():
            if re.match(pattern, barcode_data):
                info.update(data)
                break
        
        return info if info else None
    except Exception as e:
        st.error(f"Error extracting product info: {e}")
        return None
# =============================================
# Unknown Products Management
# =============================================

def unknown_products():
    """Manage unknown products detected from scanning"""
    if not check_permission("scan_products"):
        st.warning("You don't have permission to access this section")
        return
    
    st.subheader("❓ Unknown Products")
    
    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            options=["All", "Pending", "Processed", "Ignored"],
            key="unknown_status_filter"
        )
    with col2:
        date_filter = st.date_input(
            "Filter by Date",
            value=None,
            key="unknown_date_filter"
        )
    
    # Get filtered unknown products
    unknown_products = db.get_unknown_products()
    
    if status_filter != "All":
        unknown_products = [up for up in unknown_products if up['status'] == status_filter.lower()]
    
    if date_filter:
        date_str = date_filter.strftime("%Y-%m-%d")
        unknown_products = [up for up in unknown_products if up['detected_at'].startswith(date_str)]
    
    if unknown_products:
        for product in unknown_products:
            with st.expander(f"Barcode: {product['barcode']} - {product['barcode_type']}"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**Detected At:** {product['detected_at']}")
                    st.write("**Detected Info:**")
                    st.json(product.get('detected_info', {}))
                    
                    if product['status'] == 'pending':
                        st.warning("Status: Pending Review")
                    elif product['status'] == 'processed':
                        st.success("Status: Processed")
                    else:
                        st.info("Status: Ignored")
                
                with col2:
                    if product['status'] == 'pending':
                        with st.form(f"process_{product['id']}"):
                            st.write("### Create Product")
                            
                            # Pre-fill form with detected info if available
                            detected_info = product.get('detected_info', {})
                            default_name = detected_info.get('name', '')
                            default_brand = detected_info.get('brand', '')
                            default_category = detected_info.get('category', '')
                            
                            name = st.text_input("Product Name*", value=default_name, key=f"prod_name_{product['id']}")
                            price = st.number_input("Price*", min_value=0.0, step=0.01, key=f"prod_price_{product['id']}")
                            quantity = st.number_input("Quantity", min_value=0, value=1, key=f"prod_qty_{product['id']}")
                            
                            # Category selection
                            categories = db.get_categories()
                            category_options = [c['id'] for c in categories]
                            category_names = [c['name'] for c in categories]
                            
                            # Try to find matching category
                            category_index = 0
                            if default_category:
                                for i, category_name in enumerate(category_names):
                                    if default_category.lower() in category_name.lower():
                                        category_index = i
                                        break
                            
                            category_id = st.selectbox(
                                "Category",
                                options=category_options,
                                format_func=lambda x: next(c['name'] for c in categories if c['id'] == x),
                                index=category_index,
                                key=f"prod_cat_{product['id']}"
                            )
                            
                            # Brand selection
                            brands = db.get_brands()
                            brand_options = [b['id'] for b in brands]
                            brand_names = [b['name'] for b in brands]
                            
                            # Try to find matching brand
                            brand_index = 0
                            if default_brand:
                                for i, brand_name in enumerate(brand_names):
                                    if default_brand.lower() in brand_name.lower():
                                        brand_index = i
                                        break
                            
                            brand_id = st.selectbox(
                                "Brand",
                                options=brand_options,
                                format_func=lambda x: next(b['name'] for b in brands if b['id'] == x),
                                index=brand_index,
                                key=f"prod_brand_{product['id']}"
                            )
                            
                            if st.form_submit_button("Create Product"):
                                if not name or not price:
                                    st.error("Name and price are required")
                                else:
                                    item_data = {
                                        'name': name,
                                        'price': price,
                                        'quantity': quantity,
                                        'barcode': product['barcode'],
                                        'category_id': category_id,
                                        'brand_id': brand_id,
                                        'unknown_product_id': product['id']
                                    }
                                    
                                    if db.add_inventory_item(item_data):
                                        st.success("Product created and linked to barcode!")
                                        time.sleep(1)
                                        st.rerun()
                        
                        if st.button("Ignore", key=f"ignore_{product['id']}"):
                            db.update_unknown_product(product['id'], {'status': 'ignored'})
                            st.rerun()
                    else:
                        if st.button("Delete Record", key=f"delete_{product['id']}"):
                            db.delete_unknown_product(product['id'])
                            st.rerun()
    else:
        st.info("No unknown products detected")

# =============================================
# Reports & Analytics
# =============================================

def reports_and_analytics():
    """Reports and analytics dashboard"""
    if not check_permission("view_analytics"):
        st.warning("You don't have permission to access this section")
        return
    
    st.subheader("📊 Reports & Analytics")
    
    # Check if analytics is enabled
    if db.get_setting('enable_analytics', 'true').lower() != 'true':
        st.warning("Analytics is currently disabled in system settings")
        return
    
    tab1, tab2, tab3= st.tabs(["Inventory Reports", "Sales Reports", "Financial Reports"])
    
    with tab1:
        st.write("### Inventory Reports")
        
        # Inventory summary
        col1, col2, col3 = st.columns(3)
        with col1:
            total_items = len(db.get_inventory_items())
            st.metric("Total Products", total_items)
        with col2:
            low_stock = len([i for i in db.get_inventory_items() if i['quantity'] < i.get('min_stock', 5)])
            st.metric("Low Stock Items", low_stock, delta_color="inverse")
        with col3:
            total_value = sum(i['quantity'] * i['price'] for i in db.get_inventory_items())
            st.metric("Total Inventory Value", f"${total_value:,.2f}" if total_value else "$0.00")
        
        # Inventory by category
        st.write("#### Inventory by Category")
        inventory_items = db.get_inventory_items()
        if inventory_items:
            # Create DataFrame
            df = pd.DataFrame(inventory_items)
            
            # Add category names
            df['category'] = df['category_id'].apply(
                lambda x: next((c['name'] for c in db.get_categories() if c['id'] == x), 'Uncategorized')
            )
            
            # Group by category
            category_stats = df.groupby('category').agg({
                'quantity': 'sum',
                'price': 'mean',
                'id': 'count'
            }).rename(columns={'id': 'count'}).reset_index()
            
            # Display charts
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Products by Category**")
                fig = px.pie(category_stats, values='count', names='category', hole=0.3)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.write("**Inventory Value by Category**")
                category_stats['total_value'] = category_stats['quantity'] * category_stats['price']
                fig = px.bar(category_stats, x='category', y='total_value', 
                            labels={'total_value': 'Total Value', 'category': 'Category'})
                st.plotly_chart(fig, use_container_width=True)
            
            # Low stock report
            st.write("#### Low Stock Report")
            low_stock_items = [i for i in inventory_items if i['quantity'] < i.get('min_stock', 5)]
            if low_stock_items:
                low_stock_df = pd.DataFrame(low_stock_items)
                low_stock_df['category'] = low_stock_df['category_id'].apply(
                    lambda x: next((c['name'] for c in db.get_categories() if c['id'] == x), 'Uncategorized')
                )
                low_stock_df['brand'] = low_stock_df['brand_id'].apply(
                    lambda x: next((b['name'] for b in db.get_brands() if b['id'] == x), 'Unknown')
                )
                
                st.dataframe(
                    low_stock_df[['name', 'brand', 'category', 'quantity', 'min_stock']],
                    column_config={
                        "name": "Product",
                        "brand": "Brand",
                        "category": "Category",
                        "quantity": "Current Qty",
                        "min_stock": "Min Stock"
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                # Export button
                if st.button("Export Low Stock Report", key="export_low_stock"):
                    export_report(low_stock_df[['name', 'brand', 'category', 'quantity', 'min_stock']], 
                                "low_stock_report")
            else:
                st.info("No low stock items found")
        else:
            st.info("No inventory items found")
    
    with tab2:
        st.write("### Sales Reports")
        
        # Sales summary
        invoices = db.get_invoices()
        if invoices:
            # Calculate sales metrics
            total_sales = sum(i.get('total_amount', 0) for i in invoices if i.get('status') == 'paid')
            total_invoices = len(invoices)
            paid_invoices = len([i for i in invoices if i.get('status') == 'paid'])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Sales", f"${total_sales:,.2f}" if total_sales else "$0.00")
            with col2:
                st.metric("Total Invoices", total_invoices)
            with col3:
                st.metric("Paid Invoices", paid_invoices)
            
            # Sales over time
            st.write("#### Sales Over Time")
            
            # Create DataFrame
            sales_df = pd.DataFrame(invoices)
            sales_df['date'] = pd.to_datetime(sales_df['created_at']).dt.date
            sales_df = sales_df[sales_df['status'] == 'paid']
            
            if not sales_df.empty:
                # Group by date
                daily_sales = sales_df.groupby('date').agg({
                    'total_amount': 'sum'
                }).reset_index()
                
                fig = px.line(daily_sales, x='date', y='total_amount', 
                            labels={'total_amount': 'Sales Amount', 'date': 'Date'},
                            title="Daily Sales")
                st.plotly_chart(fig, use_container_width=True)
                
                # Top selling products
                st.write("#### Top Selling Products")
                
                # Get all invoice items for paid invoices
                invoice_items = []
                for invoice in invoices:
                    if invoice.get('status') == 'paid':
                        items = db.get_invoice_items(invoice['id'])
                        for item in items:
                            item['invoice_date'] = invoice['created_at']
                            invoice_items.append(item)
                
                if invoice_items:
                    items_df = pd.DataFrame(invoice_items)
                    
                    # Get product names
                    items_df['product_name'] = items_df['item_id'].apply(
                        lambda x: (db.get_inventory_item(x) or {}).get('name', 'Unknown')
                    )
                    
                    # Group by product
                    product_sales = items_df.groupby('product_name').agg({
                        'quantity': 'sum',
                        'unit_price': 'mean',
                        'id': 'count'
                    }).rename(columns={'id': 'sales_count'}).reset_index()
                    
                    # Display top 10 products
                    top_products = product_sales.sort_values('quantity', ascending=False).head(10)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Top Products by Quantity Sold**")
                        fig = px.bar(top_products, x='product_name', y='quantity',
                                    labels={'product_name': 'Product', 'quantity': 'Quantity Sold'})
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        st.write("**Top Products by Revenue**")
                        top_products['revenue'] = top_products['quantity'] * top_products['unit_price']
                        top_revenue = top_products.sort_values('revenue', ascending=False).head(10)
                        fig = px.bar(top_revenue, x='product_name', y='revenue',
                                    labels={'product_name': 'Product', 'revenue': 'Revenue'})
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Export button
                    if st.button("Export Sales Report", key="export_sales"):
                        export_report(product_sales, "sales_report")
                else:
                    st.info("No sales data available")
            else:
                st.info("No sales data available")
        else:
            st.info("No invoices found")
    
    with tab3:
        st.write("### Financial Reports")
        
        # Financial summary
        transactions = db.get_transactions()
        payments = db.get_payments()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            total_income = sum(t['amount'] for t in transactions if t['type'] == 'income')
            st.metric("Total Income", f"${total_income:,.2f}" if total_income else "$0.00")
        with col2:
            total_expenses = sum(t['amount'] for t in transactions if t['type'] == 'expense')
            st.metric("Total Expenses", f"${total_expenses:,.2f}" if total_expenses else "$0.00")
        with col3:
            net_profit = total_income - total_expenses
            st.metric("Net Profit", f"${net_profit:,.2f}" if net_profit else "$0.00")
        
        # Income vs Expenses
        st.write("#### Income vs Expenses")
        
        if transactions:
            # Create DataFrame
            trans_df = pd.DataFrame(transactions)
            trans_df['date'] = pd.to_datetime(trans_df['created_at']).dt.date
            
            # Group by date and type
            financials = trans_df.groupby(['date', 'type']).agg({
                'amount': 'sum'
            }).reset_index()
            
            # Pivot for chart
            financials_pivot = financials.pivot(index='date', columns='type', values='amount').fillna(0)
            
            fig = px.line(financials_pivot, labels={'value': 'Amount', 'date': 'Date'},
                         title="Daily Income and Expenses")
            st.plotly_chart(fig, use_container_width=True)
            
            # Payment methods
            st.write("#### Payment Methods")
            
            if payments:
                payments_df = pd.DataFrame(payments)
                payment_counts = payments_df['method'].value_counts().reset_index()
                payment_counts.columns = ['method', 'count']
                
                fig = px.pie(payment_counts, values='count', names='method',
                            title="Payment Methods Distribution")
                st.plotly_chart(fig, use_container_width=True)
                
                # Export button
                if st.button("Export Financial Report", key="export_financial"):
                    export_report(financials, "financial_report")
            else:
                st.info("No payment data available")
        else:
            st.info("No financial transactions found")
    

def export_report(data, report_name):
    """Export report data to CSV or Excel"""
    try:
        # Create export directory if it doesn't exist
        export_path = db.get_setting('report_export_path', 'reports')
        os.makedirs(export_path, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_name}_{timestamp}"
        
        # Export options
        export_format = st.radio(
            "Export Format",
            options=["CSV", "Excel"],
            horizontal=True,
            key=f"export_format_{report_name}"
        )
        
        if export_format == "CSV":
            filepath = os.path.join(export_path, f"{filename}.csv")
            data.to_csv(filepath, index=False)
        else:
            filepath = os.path.join(export_path, f"{filename}.xlsx")
            data.to_excel(filepath, index=False)
        
        # Provide download link
        with open(filepath, "rb") as f:
            bytes_data = f.read()
            st.download_button(
                label="Download Report",
                data=bytes_data,
                file_name=os.path.basename(filepath),
                mime="application/octet-stream"
            )
        
        st.success(f"Report exported successfully to {filepath}")
    except Exception as e:
        st.error(f"Error exporting report: {e}")

# =============================================
# Invoice PDF Generation
# =============================================

def generate_invoice_pdf(invoice_number: str):
    """Generate a PDF invoice"""
    try:
        invoice = db.get_invoice_by_number(invoice_number)
        if not invoice:
            st.error("Invoice not found")
            return None
            
        details = db.get_invoice_details(invoice['id'])
        if not details:
            return None
        
        # Create a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_path = temp_file.name
        temp_file.close()
        
        # Create PDF document
        doc = SimpleDocTemplate(temp_path, pagesize=letter)
        
        # Get company info from settings
        company_name = db.get_setting('company_name', 'My Company')
        company_address = db.get_setting('company_address', '')
        company_phone = db.get_setting('company_phone', '')
        company_email = db.get_setting('company_email', '')
        company_logo = db.get_setting('company_logo', '')
        invoice_header = db.get_setting('invoice_header', 'INVOICE')
        invoice_subheader = db.get_setting('invoice_subheader', '')
        invoice_footer = db.get_setting('invoice_footer', '')
        currency_symbol = db.get_setting('currency_symbol', '$')
        
        # Define styles
        styles = getSampleStyleSheet()
        
        # Prepare data for PDF
        elements = []
        
        # Add header with logo
        header_elements = []
        
        if company_logo and os.path.exists(company_logo):
            try:
                logo = Image(company_logo, width=120, height=60)
                header_elements.append(logo)
            except:
                pass
        
        header_text = [
            Paragraph(company_name, styles['Title']),
            Paragraph(company_address, styles['Normal']),
            Paragraph(f"Phone: {company_phone} | Email: {company_email}", styles['Normal'])
        ]
        
        header_table = Table([[header_elements, header_text]], colWidths=[150, 400])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ]))
        
        elements.append(header_table)
        
        # Add invoice title and details
        elements.append(Paragraph(invoice_header, styles['Heading1']))
        if invoice_subheader:
            elements.append(Paragraph(invoice_subheader, styles['Normal']))
        
        invoice_info = [
            [f"Invoice #: {details['header']['invoice_number']}", 
             f"Date: {details['header']['date']}"],
            [f"Customer: {details['header']['customer_name']}", 
             f"Due Date: {details['header']['due_date']}"],
            [f"Payment Terms: {details['header']['payment_terms']}", 
             f"Status: {details['header']['status'].capitalize()}"]
        ]
        
        invoice_table = Table(invoice_info, colWidths=[250, 250])
        invoice_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        elements.append(invoice_table)
        
        # Add line items
        line_items = [['Item', 'Qty', 'Price', 'Discount', 'Total']]
        
        for item in details['items']:
            line_items.append([
                item['item_name'],
                str(item['quantity']),
                f"{currency_symbol}{item['unit_price']:.2f}",
                f"{currency_symbol}{item['discount']:.2f}",
                f"{currency_symbol}{item['total_price']:.2f}"
            ])
        
        items_table = Table(line_items, colWidths=[200, 50, 80, 80, 80])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(items_table)
        
        # Add totals
        totals = [
            ['', '', '', 'Subtotal:', f"{currency_symbol}{details['header']['subtotal']:.2f}"],
            ['', '', '', 'Discount:', f"{currency_symbol}{details['header']['discount']:.2f}"],
            ['', '', '', 'Tax:', f"{currency_symbol}{details['header']['tax']:.2f}"],
            ['', '', '', 'Shipping:', f"{currency_symbol}{details['header']['shipping_cost']:.2f}"],
            ['', '', '', 'Total:', f"{currency_symbol}{details['header']['total']:.2f}"]
        ]
        
        totals_table = Table(totals, colWidths=[200, 50, 80, 80, 80])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEABOVE', (3, -1), (4, -1), 1, colors.black),
            ('FONT', (3, -1), (4, -1), 'Helvetica-Bold'),
        ]))
        elements.append(totals_table)
        
        # Add notes if exists
        if details['header']['notes']:
            elements.append(Paragraph("Notes:", styles['Heading3']))
            elements.append(Paragraph(details['header']['notes'], styles['Normal']))
        
        # Add footer
        if invoice_footer:
            elements.append(Paragraph(invoice_footer, styles['Italic']))
        
        # Build the PDF
        doc.build(elements)
        
        return temp_path
    except Exception as e:
        st.error(f"Error generating PDF: {e}")
        return None

# =============================================
# System Settings Management UI
# =============================================

def system_settings():
    """System settings management interface with complete backup functionality"""
    if not check_permission("admin"):
        st.warning("You don't have permission to access this section")
        return
    
    st.subheader("⚙️ System Settings")
    
    tab1, tab2, tab3, tab4 = st.tabs(["General", "Invoice", "Tax", "Backup"])
    
    with tab1:
        st.write("### General Settings")
        settings = db.get_all_settings()
        general_settings = [s for s in settings if s['setting_name'] in [
            'company_name', 'company_address', 'company_phone', 'company_email',
            'currency_symbol', 'currency_code', 'barcode_prefix',
            'low_stock_threshold', 'auto_detect_products', 'auto_create_unknown_products',
            'enable_barcode_scanning', 'enable_analytics', 'enable_auto_backup',
            'report_export_path'
        ]]
        
        with st.form("general_settings_form"):
            cols = st.columns(2)
            col_idx = 0
            for setting in general_settings:
                with cols[col_idx]:
                    if setting['setting_name'] in ['auto_detect_products', 'auto_create_unknown_products', 
                                                'enable_barcode_scanning', 'enable_analytics', 'enable_auto_backup']:
                        value = st.checkbox(
                            setting['setting_name'].replace('_', ' ').title(),
                            value=setting['setting_value'].lower() == 'true',
                            key=f"gen_set_{setting['setting_name']}"
                        )
                        setting['setting_value'] = str(value).lower()
                    else:
                        setting['setting_value'] = st.text_input(
                            setting['setting_name'].replace('_', ' ').title(),
                            value=setting['setting_value'],
                            key=f"gen_set_{setting['setting_name']}"
                        )
                col_idx = (col_idx + 1) % 2
            
            if st.form_submit_button("Save General Settings"):
                for setting in general_settings:
                    db.update_setting(setting['setting_name'], setting['setting_value'])
                st.success("General settings updated successfully!")

    with tab2:
        st.write("### Invoice Settings")
        invoice_settings = [s for s in settings if s['setting_name'] in [
            'invoice_prefix', 'invoice_header', 'invoice_subheader', 'invoice_footer'
        ]]
        
        with st.form("invoice_settings_form"):
            cols = st.columns(2)
            col_idx = 0
            for setting in invoice_settings:
                with cols[col_idx]:
                    if setting['setting_name'] == 'invoice_footer':
                        setting['setting_value'] = st.text_area(
                            setting['setting_name'].replace('_', ' ').title(),
                            value=setting['setting_value'],
                            key=f"inv_set_{setting['setting_name']}"
                        )
                    else:
                        setting['setting_value'] = st.text_input(
                            setting['setting_name'].replace('_', ' ').title(),
                            value=setting['setting_value'],
                            key=f"inv_set_{setting['setting_name']}"
                        )
                col_idx = (col_idx + 1) % 2
            
            current_logo = db.get_setting('company_logo')
            logo_file = st.file_uploader(
                "Company Logo",
                type=["png", "jpg", "jpeg"],
                key="company_logo_upload"
            )
            
            if current_logo and os.path.exists(current_logo):
                st.image(current_logo, caption="Current Logo", width=150)
                if st.button("Remove Logo"):
                    db.update_setting('company_logo', '')
                    st.rerun()
            
            if st.form_submit_button("Save Invoice Settings"):
                for setting in invoice_settings:
                    db.update_setting(setting['setting_name'], setting['setting_value'])
                
                if logo_file:
                    os.makedirs("uploads/logo", exist_ok=True)
                    logo_path = os.path.join("uploads/logo", f"logo_{int(time.time())}.{logo_file.name.split('.')[-1]}")
                    with open(logo_path, "wb") as f:
                        f.write(logo_file.getbuffer())
                    db.update_setting('company_logo', logo_path)
                st.success("Invoice settings updated successfully!")

    with tab3:
        st.write("### Tax Settings")
        st.write("#### Tax Rates")
        tax_rates = db.get_tax_rates()
        
        with st.expander("Add New Tax Rate"):
            with st.form("add_tax_rate_form"):
                col1, col2 = st.columns(2)
                with col1:
                    name = st.text_input("Name*", key="tax_name")
                    rate = st.number_input(
                        "Rate (%)*", 
                        min_value=0.0, 
                        max_value=100.0, 
                        step=0.1,
                        key="tax_rate"
                    )
                with col2:
                    description = st.text_input("Description", key="tax_desc")
                    is_default = st.checkbox("Set as default tax rate", key="tax_default")
                
                if st.form_submit_button("Add Tax Rate"):
                    if not name or rate is None:
                        st.error("Name and rate are required")
                    else:
                        tax_data = {
                            'name': name,
                            'rate': rate,
                            'description': description,
                            'is_default': is_default
                        }
                        if db.add_tax_rate(tax_data):
                            st.success("Tax rate added successfully!")
                            time.sleep(1)
                            st.rerun()
        
        if tax_rates:
            for tax_rate in tax_rates:
                with st.expander(f"{tax_rate['name']} - {tax_rate['rate']}% {'(Default)' if tax_rate['is_default'] else ''}"):
                    col3, col4 = st.columns([3, 1])
                    with col3:
                        st.write(f"**Description:** {tax_rate.get('description', '')}")
                    with col4:
                        if not tax_rate['is_default']:
                            if st.button(f"Set as Default", key=f"set_default_{tax_rate['id']}"):
                                db.update_tax_rate(tax_rate['id'], {'is_default': True})
                                st.rerun()
                        if st.button(f"Delete", key=f"delete_tax_{tax_rate['id']}"):
                            success, message = db.delete_tax_rate(tax_rate['id'])
                            if success:
                                st.success(message)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(message)
        else:
            st.info("No tax rates configured")

    with tab4:
        st.write("### Backup & Restore")
        
        # Backup configuration
        with st.expander("Backup Configuration"):
            with st.form("backup_config_form"):
                auto_backup = st.checkbox(
                    "Enable Automatic Backups",
                    value=db.get_setting('enable_auto_backup', 'false').lower() == 'true'
                )
                backup_frequency = st.selectbox(
                    "Backup Frequency",
                    options=["Daily", "Weekly", "Monthly"],
                    index=0
                )
                max_backups = st.number_input(
                    "Maximum Backups to Keep",
                    min_value=1,
                    max_value=100,
                    value=30
                )
                
                if st.form_submit_button("Save Backup Settings"):
                    db.update_setting('enable_auto_backup', str(auto_backup).lower())
                    db.update_setting('backup_frequency', backup_frequency)
                    db.update_setting('max_backups', str(max_backups))
                    st.success("Backup settings updated!")

        # Create comprehensive backup
        with st.form("create_backup_form"):
            st.write("#### Create Complete System Backup")
            backup_name = st.text_input(
                "Backup Name", 
                value=f"full_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            backup_description = st.text_area("Description (optional)")
            
            include_options = st.columns(2)
            with include_options[0]:
                include_users = st.checkbox("Include Users", value=True)
                include_products = st.checkbox("Include Products", value=True)
                include_transactions = st.checkbox("Include Transactions", value=True)
            with include_options[1]:
                include_customers = st.checkbox("Include Customers", value=True)
                include_settings = st.checkbox("Include Settings", value=True)
                include_tax_rates = st.checkbox("Include Tax Rates", value=True)
            
            if st.form_submit_button("Create Backup Now"):
                with st.spinner("Creating system backup..."):
                    backup_data = {
                        "metadata": {
                            "backup_name": backup_name,
                            "created_at": datetime.datetime.now().isoformat(),
                            "description": backup_description,
                            "system_version": "1.0"
                        }
                    }
                    
                    if include_settings:
                        backup_data["settings"] = db.get_all_settings()
                    if include_users:
                        backup_data["users"] = db.get_users()
                    if include_products:
                        backup_data["products"] = db.get_inventory_items()
                    if include_customers:
                        backup_data["customers"] = db.get_customers()
                    if include_transactions:
                        backup_data["transactions"] = db.get_transactions()
                    if include_tax_rates:
                        backup_data["tax_rates"] = db.get_tax_rates()
                    
                    # Create the backup
                    backup_id = db.create_backup(backup_name=backup_name, backup_data=json.dumps(backup_data))
                    if backup_id:
                        st.success("System backup created successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Failed to create backup")

        # Backup upload and restore
        st.write("#### Backup Management")
        
        # Upload backup
        with st.expander("Upload Backup File"):
            uploaded_file = st.file_uploader(
                "Select a backup file to upload", 
                type=["json"],
                key="backup_uploader"
            )
            
            if uploaded_file is not None:
                try:
                    backup_content = json.load(uploaded_file)
                    st.info(f"Backup file loaded: {uploaded_file.name}")
                    
                    # Validate backup structure
                    required_sections = ["settings", "users", "products", "customers", "transactions"]
                    valid_backup = all(section in backup_content for section in required_sections)
                    
                    if st.button("Import Backup"):
                        if valid_backup:
                            backup_name = f"restored_{uploaded_file.name.split('.')[0]}_{datetime.datetime.now().strftime('%Y%m%d')}"
                            backup_id = db.create_backup(
                                backup_name=backup_name, 
                                backup_data=json.dumps(backup_content)
                            )
                            if backup_id:
                                st.success("Backup uploaded successfully!")
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.error("Invalid backup format. Missing required sections.")
                except json.JSONDecodeError:
                    st.error("Invalid JSON file format")
                except Exception as e:
                    st.error(f"Error processing backup file: {str(e)}")

        # List and manage backups
        st.write("#### Available Backups")
        backups = db.data['backups']  # Access backups directly from database
        
        if backups:
            for backup in backups:
                with st.expander(f"{backup['name']} - {backup['created_at']}"):
                    try:
                        backup_data = json.loads(backup['data'])
                        st.write(f"**Description:** {backup_data.get('metadata', {}).get('description', 'No description')}")
                        st.write(f"**Contains:**")
                        
                        cols = st.columns(3)
                        with cols[0]:
                            if 'users' in backup_data:
                                st.write(f"👥 {len(backup_data['users'])} users")
                            if 'settings' in backup_data:
                                st.write(f"⚙️ {len(backup_data['settings'])} settings")
                        with cols[1]:
                            if 'products' in backup_data:
                                st.write(f"🛍️ {len(backup_data['products'])} products")
                            if 'tax_rates' in backup_data:
                                st.write(f"💰 {len(backup_data['tax_rates'])} tax rates")
                        with cols[2]:
                            if 'customers' in backup_data:
                                st.write(f"👤 {len(backup_data['customers'])} customers")
                            if 'transactions' in backup_data:
                                st.write(f"🧾 {len(backup_data['transactions'])} transactions")
                    except:
                        st.warning("Could not parse backup details")
                    
                    # Backup actions
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("🔄 Restore", key=f"restore_{backup['id']}"):
                            if st.warning("This will overwrite current system data. Continue?"):
                                success, message = db.restore_backup(backup['id'])
                                if success:
                                    st.success(message)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(message)
                    with col2:
                        st.download_button(
                            label="📥 Download",
                            data=backup['data'],
                            file_name=f"{backup['name']}.json",
                            mime="application/json",
                            key=f"download_{backup['id']}"
                        )
                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_{backup['id']}"):
                            if st.warning("Delete this backup permanently?"):
                                success, message = db.delete_backup(backup['id'])
                                if success:
                                    st.success(message)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(message)
        else:
            st.info("No backups available in the system")

# =============================================
# User Management UI
# =============================================

def user_management():
    """User management interface"""
    if not check_permission("admin"):
        st.warning("You don't have permission to access this section")
        return
    
    st.subheader("👥 User Management")
    
    # Add new user
    with st.expander("Add New User"):
        with st.form("add_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                username = st.text_input("Username*", key="user_username")
                email = st.text_input("Email", key="user_email")
            with col2:
                password = st.text_input("Password*", type="password", key="user_password")
                role = st.selectbox(
                    "Role",
                    options=["Admin", "Manager", "Sales", "Warehouse"],
                    key="user_role"
                )
            
            is_active = st.checkbox("Active", value=True, key="user_active")
            
            if st.form_submit_button("Add User"):
                if not username or not password:
                    st.error("Username and password are required")
                else:
                    user_data = {
                        'username': username,
                        'password': password,
                        'email': email,
                        'role': role,
                        'is_active': is_active
                    }
                    
                    if db.add_user(user_data):
                        st.success("User added successfully!")
                        time.sleep(1)
                        st.rerun()
    
    # List users
    st.write("### User List")
    users = db.get_users()
    
    if users:
        for user in users:
            with st.expander(f"{user['username']} ({user['role']})"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**Email:** {user.get('email', '')}")
                    st.write(f"**Status:** {'Active' if user.get('is_active', True) else 'Inactive'}")
                    st.write(f"**Last Login:** {user.get('last_login', 'Never')}")
                
                with col2:
                    # Edit user
                    with st.popover("Edit"):
                        with st.form(f"edit_user_{user['id']}"):
                            new_email = st.text_input(
                                "Email", 
                                value=user.get('email', ''),
                                key=f"edit_email_{user['id']}"
                            )
                            new_role = st.selectbox(
                                "Role",
                                options=["Admin", "Manager", "Sales", "Warehouse"],
                                index=["Admin", "Manager", "Sales", "Warehouse"].index(user['role']),
                                key=f"edit_role_{user['id']}"
                            )
                            new_status = st.checkbox(
                                "Active",
                                value=user.get('is_active', True),
                                key=f"edit_status_{user['id']}"
                            )
                            
                            new_password = st.text_input(
                                "New Password (leave blank to keep current)",
                                type="password",
                                key=f"edit_password_{user['id']}"
                            )
                            
                            if st.form_submit_button("Update"):
                                update_data = {
                                    'email': new_email,
                                    'role': new_role,
                                    'is_active': new_status
                                }
                                
                                if new_password:
                                    update_data['password'] = new_password
                                
                                if db.update_user(user['id'], update_data):
                                    st.success("User updated!")
                                    time.sleep(1)
                                    st.rerun()
                    
                    # Delete user (can't delete yourself)
                    if user['id'] != st.session_state.user_id:
                        if st.button("Delete", key=f"delete_{user['id']}"):
                            success, message = db.delete_user(user['id'])
                            if success:
                                st.success(message)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(message)
                    else:
                        st.info("Cannot delete your own account")
    else:
        st.info("No users found")

# =============================================
# Inventory Dashboard
# =============================================

# =============================================
# COMPLETE INVENTORY MANAGEMENT MODULE
# =============================================

# =============================================
# COMPLETE INVENTORY MANAGEMENT MODULE
# =============================================

def inventory_dashboard():
    """Inventory management with deduct stock functionality"""
    st.subheader("📦 Inventory Management")
    
    # Quick stats cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        total_items = len(db.get_inventory_items())
        st.metric("Total Products", total_items)
    with col2:
        low_stock = len([i for i in db.get_inventory_items() if i['quantity'] < i.get('min_stock', 5)])
        st.metric("Low Stock", low_stock, delta_color="inverse")
    with col3:
        out_of_stock = len([i for i in db.get_inventory_items() if i['quantity'] <= 0])
        st.metric("Out of Stock", out_of_stock, delta_color="inverse")
    with col4:
        total_value = sum(i['quantity'] * i['price'] for i in db.get_inventory_items())
        st.metric("Total Value", f"${total_value:,.2f}")

    # Main tabs
    tab1, tab2, tab3, tab4 = st.tabs(["Products", "Add Product", "Bulk Operations", "Stock Movement"])

    with tab1:
        st.write("### Product Inventory")
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            category_filter = st.selectbox(
                "Category",
                ["All"] + [c['name'] for c in db.get_categories()],
                key="prod_category_filter"
            )
        with col2:
            stock_filter = st.selectbox(
                "Stock Status",
                ["All", "In Stock", "Low Stock", "Out of Stock"],
                key="prod_stock_filter"
            )
        with col3:
            search_query = st.text_input("Search Products", key="prod_search")

        # Get filtered products
        products = db.get_inventory_items()
        
        if category_filter != "All":
            category_id = next(c['id'] for c in db.get_categories() if c['name'] == category_filter)
            products = [p for p in products if p.get('category_id') == category_id]

        if stock_filter != "All":
            if stock_filter == "Low Stock":
                products = [p for p in products if p['quantity'] < p.get('min_stock', 5)]
            elif stock_filter == "Out of Stock":
                products = [p for p in products if p['quantity'] <= 0]
            else:
                products = [p for p in products if p['quantity'] > 0]

        if search_query:
            products = [p for p in products if search_query.lower() in p['name'].lower()]

        # Display products
        if products:
            for product in products:
                with st.expander(f"{product['name']} - Stock: {product['quantity']}", expanded=False):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        # Display product info
                        st.write(f"**Price:** ${product['price']:.2f}")
                        st.write(f"**SKU:** {product.get('sku', 'N/A')}")
                        st.write(f"**Barcode:** {product.get('barcode', 'N/A')}")
                        
                        # Stock alert
                        if product['quantity'] <= 0:
                            st.error("Out of Stock")
                        elif product['quantity'] < product.get('min_stock', 5):
                            st.warning(f"Low Stock (Min: {product.get('min_stock', 5)})")
                    
                    with col2:
                        # Deduct stock button
                        if st.button("📉 Deduct Stock", key=f"deduct_{product['id']}"):
                            with st.popover("Deduct Inventory"):
                                with st.form(f"deduct_form_{product['id']}"):
                                    deduct_qty = st.number_input(
                                        "Quantity to Deduct",
                                        min_value=1,
                                        max_value=product['quantity'],
                                        value=1,
                                        key=f"deduct_qty_{product['id']}"
                                    )
                                    reason = st.text_input("Reason", key=f"deduct_reason_{product['id']}")
                                    
                                    if st.form_submit_button("Confirm Deduction"):
                                        new_qty = product['quantity'] - deduct_qty
                                        if new_qty < 0:
                                            new_qty = 0
                                        db.update_inventory_item(product['id'], {'quantity': new_qty})
                                        db.log_audit(
                                            st.session_state.user_id,
                                            "stock_deducted",
                                            f"Deducted {deduct_qty} of {product['name']}. Reason: {reason}"
                                        )
                                        st.success(f"Stock updated! New quantity: {new_qty}")
                                        time.sleep(1)
                                        st.rerun()
                        
                        # Edit button
                        if st.button("✏️ Edit", key=f"edit_{product['id']}"):
                            st.session_state.edit_product = product
                            st.rerun()
                        
                        # Delete button
                        if st.button("🗑️ Delete", key=f"del_{product['id']}"):
                            st.session_state.delete_product = product
                            st.rerun()

            # Edit product modal
            if 'edit_product' in st.session_state:
                with st.container(border=True):
                    st.write("### Edit Product")
                    edit_product_form(st.session_state.edit_product)
            
            # Delete confirmation modal
            if 'delete_product' in st.session_state:
                with st.container(border=True):
                    st.warning(f"Delete {st.session_state.delete_product['name']}?")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Confirm Delete", type="primary"):
                            db.delete_inventory_item(st.session_state.delete_product['id'])
                            db.log_audit(
                                st.session_state.user_id,
                                "product_deleted",
                                f"Deleted product: {st.session_state.delete_product['name']}"
                            )
                            del st.session_state.delete_product
                            st.rerun()
                    with col2:
                        if st.button("Cancel"):
                            del st.session_state.delete_product
                            st.rerun()
        else:
            st.info("No products found matching filters")

    # =========================================
    # TAB 2: ADD NEW PRODUCT
    # =========================================
    with tab2:
        add_product_form()

    # =========================================
    # TAB 3: BULK OPERATIONS - FIXED
    # =========================================
    with tab3:
        st.write("### Bulk Operations")
        
        # Bulk import section
        with st.expander("📤 Bulk Import", expanded=True):
            st.write("#### Import from CSV Template")
            
            # Download template
            template_data = {
                "name": ["Product 1", "Product 2"],
                "description": ["Description 1", "Description 2"],
                "category": ["Electronics", "Clothing"],
                "subcategory": ["Phones", "Shirts"],
                "brand": ["Apple", "Nike"],
                "price": [999.99, 49.99],
                "cost": [800.00, 30.00],
                "quantity": [10, 25],
                "min_stock": [5, 10],
                "barcode": ["123456789", "987654321"],
                "supplier": ["Supplier A", "Supplier B"]
            }
            template_df = pd.DataFrame(template_data)
            
            st.download_button(
                "Download CSV Template",
                template_df.to_csv(index=False),
                "inventory_import_template.csv",
                "text/csv"
            )
            
            # File upload
            uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
            if uploaded_file:
                try:
                    import_df = pd.read_csv(uploaded_file)
                    st.write("Preview:")
                    st.dataframe(import_df.head(3))
                    
                    if st.button("Process Import"):
                        with st.spinner("Importing products..."):
                            success_count = 0
                            error_count = 0
                            error_messages = []
                            
                            for idx, row in import_df.iterrows():
                                try:
                                    # Get category ID
                                    category = next((c for c in db.get_categories() if c['name'].lower() == str(row['category']).lower()), None)
                                    category_id = category['id'] if category else None
                                    
                                    # Get brand ID
                                    brand = next((b for b in db.get_brands() if b['name'].lower() == str(row['brand']).lower()), None)
                                    brand_id = brand['id'] if brand else None
                                    
                                    # Get supplier ID
                                    supplier = next((s for s in db.get_suppliers() if s['name'].lower() == str(row['supplier']).lower()), None)
                                    supplier_id = supplier['id'] if supplier else None
                                    
                                    # Handle NaN values with proper defaults
                                    name = str(row['name']) if pd.notna(row['name']) else f"Imported Product {idx+1}"
                                    description = str(row['description']) if pd.notna(row.get('description')) else ""
                                    
                                    # Handle numeric values with NaN protection
                                    price = float(row['price']) if pd.notna(row['price']) else 0.0
                                    cost = float(row['cost']) if pd.notna(row.get('cost')) else 0.0
                                    
                                    # Handle integer values with NaN protection
                                    quantity = int(row['quantity']) if pd.notna(row.get('quantity')) else 0
                                    min_stock = int(row['min_stock']) if pd.notna(row.get('min_stock')) else 5
                                    
                                    # Handle barcode
                                    barcode = str(row['barcode']) if pd.notna(row.get('barcode')) else ""
                                    
                                    product_data = {
                                        'name': name,
                                        'description': description,
                                        'price': price,
                                        'cost': cost,
                                        'quantity': quantity,
                                        'min_stock': min_stock,
                                        'barcode': barcode,
                                        'category_id': category_id,
                                        'brand_id': brand_id,
                                        'supplier_id': supplier_id
                                    }
                                    
                                    if db.add_inventory_item(product_data):
                                        success_count += 1
                                except Exception as e:
                                    error_count += 1
                                    error_messages.append(f"Row {idx+1}: {str(e)}")
                                    continue
                            
                            # Show import results
                            if success_count > 0:
                                st.success(f"Successfully imported {success_count}/{len(import_df)} products")
                            
                            if error_count > 0:
                                st.error(f"Failed to import {error_count} products")
                                with st.expander("Show error details"):
                                    for error in error_messages:
                                        st.write(error)
                                    
                except Exception as e:
                    st.error(f"Import error: {str(e)}")
        
        # Bulk update section
        with st.expander("🔄 Bulk Update", expanded=False):
            with st.form("bulk_update_form"):
                st.write("Update multiple products at once")
                
                # Filter for bulk update
                col1, col2 = st.columns(2)
                with col1:
                    bulk_category = st.selectbox(
                        "Filter by Category",
                        ["All"] + [c['name'] for c in db.get_categories()],
                        key="bulk_update_category"
                    )
                with col2:
                    bulk_brand = st.selectbox(
                        "Filter by Brand",
                        ["All"] + [b['name'] for b in db.get_brands()],
                        key="bulk_update_brand"
                    )
                
                # Update fields
                st.write("Fields to update:")
                col3, col4 = st.columns(2)
                with col3:
                    new_price = st.number_input("Price", min_value=0.0, value=None, key="bulk_price")
                    new_cost = st.number_input("Cost", min_value=0.0, value=None, key="bulk_cost")
                with col4:
                    new_min_stock = st.number_input("Min Stock", min_value=0, value=None, key="bulk_min_stock")
                    new_category = st.selectbox(
                        "Category",
                        ["No Change"] + [c['name'] for c in db.get_categories()],
                        key="bulk_category_change"
                    )
                
                if st.form_submit_button("Apply Bulk Update"):
                    # Get products to update
                    products_to_update = db.get_inventory_items()
                    
                    if bulk_category != "All":
                        category_id = next(c['id'] for c in db.get_categories() if c['name'] == bulk_category)
                        products_to_update = [p for p in products_to_update if p.get('category_id') == category_id]
                    
                    if bulk_brand != "All":
                        brand_id = next(b['id'] for b in db.get_brands() if b['name'] == bulk_brand)
                        products_to_update = [p for p in products_to_update if p.get('brand_id') == brand_id]
                    
                    # Prepare update data
                    update_data = {}
                    if new_price is not None:
                        update_data['price'] = new_price
                    if new_cost is not None:
                        update_data['cost'] = new_cost
                    if new_min_stock is not None:
                        update_data['min_stock'] = new_min_stock
                    if new_category != "No Change":
                        category_id = next(c['id'] for c in db.get_categories() if c['name'] == new_category)
                        update_data['category_id'] = category_id
                    
                    if update_data:
                        updated_count = 0
                        for product in products_to_update:
                            if db.update_inventory_item(product['id'], update_data):
                                updated_count += 1
                        
                        st.success(f"Updated {updated_count} products")
                    else:
                        st.warning("No fields selected for update")

        # Bulk delete section
        with st.expander("🗑️ Bulk Delete", expanded=False):
            with st.form("bulk_delete_form"):
                st.warning("This will permanently delete selected products")
                
                # Filter for bulk delete
                col1, col2 = st.columns(2)
                with col1:
                    del_category = st.selectbox(
                        "Category",
                        ["All"] + [c['name'] for c in db.get_categories()],
                        key="bulk_del_category"
                    )
                with col2:
                    del_stock_status = st.selectbox(
                        "Stock Status",
                        ["All", "In Stock", "Out of Stock"],
                        key="bulk_del_stock"
                    )
                
                if st.form_submit_button("Preview Products for Deletion"):
                    # Get products to delete
                    products_to_delete = db.get_inventory_items()
                    
                    if del_category != "All":
                        category_id = next(c['id'] for c in db.get_categories() if c['name'] == del_category)
                        products_to_delete = [p for p in products_to_delete if p.get('category_id') == category_id]
                    
                    if del_stock_status != "All":
                        if del_stock_status == "Out of Stock":
                            products_to_delete = [p for p in products_to_delete if p['quantity'] <= 0]
                        else:
                            products_to_delete = [p for p in products_to_delete if p['quantity'] > 0]
                    
                    if products_to_delete:
                        st.warning(f"{len(products_to_delete)} products will be deleted")
                        st.dataframe(pd.DataFrame(products_to_delete)[['name', 'quantity', 'price']].head(10))
                        
                        if st.button("Confirm Bulk Delete", type="primary"):
                            deleted_count = 0
                            for product in products_to_delete:
                                if db.delete_inventory_item(product['id']):
                                    deleted_count += 1
                                    db.log_audit(
                                        st.session_state.user_id,
                                        "bulk_deleted",
                                        f"Deleted product: {product['name']}"
                                    )
                            
                            st.success(f"Deleted {deleted_count} products")
                    else:
                        st.info("No products match the selected filters")

    # =========================================
    # TAB 4: STOCK MOVEMENT
    # =========================================
    with tab4:
        st.write("### Stock Movement")
        
        # Stock adjustment types
        movement_type = st.radio(
            "Movement Type",
            ["Receive Stock", "Adjust Stock", "Transfer Stock"],
            horizontal=True
        )
        
        if movement_type == "Receive Stock":
            with st.form("receive_stock_form"):
                st.write("#### Receive New Stock")
                
                col1, col2 = st.columns(2)
                with col1:
                    product_id = st.selectbox(
                        "Product",
                        [p['id'] for p in db.get_inventory_items()],
                        format_func=lambda x: next(p['name'] for p in db.get_inventory_items() if p['id'] == x),
                        key="receive_product"
                    )
                    quantity = st.number_input("Quantity", min_value=1, value=1, key="receive_qty")
                with col2:
                    supplier_id = st.selectbox(
                        "Supplier",
                        [s['id'] for s in db.get_suppliers()],
                        format_func=lambda x: next(s['name'] for s in db.get_suppliers() if s['id'] == x),
                        key="receive_supplier"
                    )
                    batch_number = st.text_input("Batch/Lot Number", key="receive_batch")
                
                notes = st.text_area("Notes", key="receive_notes")
                
                if st.form_submit_button("Receive Stock"):
                    product = db.get_inventory_item(product_id)
                    new_qty = product['quantity'] + quantity
                    db.update_inventory_item(product_id, {'quantity': new_qty})
                    
                    # Log transaction
                    db.log_audit(
                        st.session_state.user_id,
                        "stock_received",
                        f"Received {quantity} units of {product['name']}. New stock: {new_qty}"
                    )
                    
                    st.success(f"Stock updated! New quantity: {new_qty}")
        
        elif movement_type == "Adjust Stock":
            with st.form("adjust_stock_form"):
                st.write("#### Adjust Stock Levels")
                
                col1, col2 = st.columns(2)
                with col1:
                    product_id = st.selectbox(
                        "Product",
                        [p['id'] for p in db.get_inventory_items()],
                        format_func=lambda x: next(p['name'] for p in db.get_inventory_items() if p['id'] == x),
                        key="adjust_product"
                    )
                    adjustment = st.number_input(
                        "Adjustment (+/-)",
                        min_value=-1000,
                        max_value=1000,
                        value=0,
                        key="adjust_value"
                    )
                with col2:
                    reason = st.selectbox(
                        "Reason",
                        ["Damaged", "Lost", "Found", "Miscount", "Other"],
                        key="adjust_reason"
                    )
                    if reason == "Other":
                        custom_reason = st.text_input("Specify Reason", key="adjust_custom_reason")
                
                notes = st.text_area("Notes", key="adjust_notes")
                
                if st.form_submit_button("Adjust Stock"):
                    product = db.get_inventory_item(product_id)
                    new_qty = product['quantity'] + adjustment
                    
                    if new_qty < 0:
                        st.error("Cannot have negative stock")
                    else:
                        db.update_inventory_item(product_id, {'quantity': new_qty})
                        
                        # Log transaction
                        db.log_audit(
                            st.session_state.user_id,
                            "stock_adjusted",
                            f"Adjusted {product['name']} by {adjustment}. Reason: {reason}. New stock: {new_qty}"
                        )
                        
                        st.success(f"Stock adjusted! New quantity: {new_qty}")
        
        elif movement_type == "Transfer Stock":
            with st.form("transfer_stock_form"):
                st.write("#### Transfer Between Locations")
                
                col1, col2 = st.columns(2)
                with col1:
                    product_id = st.selectbox(
                        "Product",
                        [p['id'] for p in db.get_inventory_items()],
                        format_func=lambda x: next(p['name'] for p in db.get_inventory_items() if p['id'] == x),
                        key="transfer_product"
                    )
                    quantity = st.number_input("Quantity", min_value=1, value=1, key="transfer_qty")
                with col2:
                    from_location = st.selectbox(
                        "From Location",
                        [l['id'] for l in db.get_locations()],
                        format_func=lambda x: next(l['name'] for l in db.get_locations() if l['id'] == x),
                        key="transfer_from"
                    )
                    to_location = st.selectbox(
                        "To Location",
                        [l['id'] for l in db.get_locations()],
                        format_func=lambda x: next(l['name'] for l in db.get_locations() if l['id'] == x),
                        key="transfer_to"
                    )
                
                notes = st.text_area("Transfer Notes", key="transfer_notes")
                
                if st.form_submit_button("Transfer Stock"):
                    product = db.get_inventory_item(product_id)
                    
                    # Check if product is at from_location
                    if product.get('location_id') != from_location:
                        st.error("Product is not at the selected source location")
                    elif product['quantity'] < quantity:
                        st.error("Not enough stock available for transfer")
                    else:
                        # Update source product
                        new_source_qty = product['quantity'] - quantity
                        db.update_inventory_item(product_id, {'quantity': new_source_qty})
                        
                        # Log transaction
                        db.log_audit(
                            st.session_state.user_id,
                            "stock_transferred",
                            f"Transferred {quantity} units of {product['name']} from {from_location} to {to_location}"
                        )
                        
                        st.success(f"Transferred {quantity} units to {to_location}")

# =========================================
# SUPPORTING FUNCTIONS
# =========================================

def edit_product_form(product):
    """Form for editing product details"""
    with st.form(f"edit_product_{product['id']}"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name", value=product['name'], key=f"edit_name_{product['id']}")
            description = st.text_area("Description", value=product.get('description', ''), key=f"edit_desc_{product['id']}")
            
            # Category selection
            categories = db.get_categories()
            current_category = product.get('category_id', '')
            category_idx = next((i for i, c in enumerate(categories) if c['id'] == current_category), 0)
            category_id = st.selectbox(
                "Category",
                options=[c['id'] for c in categories],
                format_func=lambda x: next(c['name'] for c in categories if c['id'] == x),
                index=category_idx,
                key=f"edit_cat_{product['id']}"
            )
            
            # Subcategory selection
            subcategories = db.get_subcategories(category_id)
            current_subcategory = product.get('subcategory_id', '')
            subcategory_idx = next((i for i, sc in enumerate(subcategories) if sc['id'] == current_subcategory), 0)
            subcategory_id = st.selectbox(
                "Subcategory",
                options=[sc['id'] for sc in subcategories],
                format_func=lambda x: next(sc['name'] for sc in subcategories if sc['id'] == x),
                index=subcategory_idx,
                key=f"edit_subcat_{product['id']}"
            )
        
        with col2:
            price = st.number_input("Price", min_value=0.0, value=float(product['price']), step=0.01, key=f"edit_price_{product['id']}")
            cost = st.number_input("Cost", min_value=0.0, value=float(product.get('cost', 0)), step=0.01, key=f"edit_cost_{product['id']}")
            quantity = st.number_input("Quantity", min_value=0, value=product['quantity'], key=f"edit_qty_{product['id']}")
            
            # Brand selection
            brands = db.get_brands()
            current_brand = product.get('brand_id', '')
            brand_idx = next((i for i, b in enumerate(brands) if b['id'] == current_brand), 0)
            brand_id = st.selectbox(
                "Brand",
                options=[b['id'] for b in brands],
                format_func=lambda x: next(b['name'] for b in brands if b['id'] == x),
                index=brand_idx,
                key=f"edit_brand_{product['id']}"
            )
        
        # Barcode section
        barcode = st.text_input("Barcode", value=product.get('barcode', ''), key=f"edit_barcode_{product['id']}")
        
        # Stock thresholds
        col3, col4 = st.columns(2)
        with col3:
            min_stock = st.number_input("Min Stock", min_value=0, value=product.get('min_stock', 5), key=f"edit_min_{product['id']}")
        with col4:
            max_stock = st.number_input("Max Stock", min_value=0, value=product.get('max_stock', 100), key=f"edit_max_{product['id']}")
        
        # Form actions
        col5, col6 = st.columns(2)
        with col5:
            submit_button = st.form_submit_button("Save Changes")
        with col6:
            cancel_button = st.form_submit_button("Cancel")
        
        if submit_button:
            update_data = {
                'name': name,
                'description': description,
                'price': price,
                'cost': cost,
                'quantity': quantity,
                'barcode': barcode,
                'category_id': category_id,
                'subcategory_id': subcategory_id if subcategory_id else None,
                'brand_id': brand_id if brand_id else None,
                'min_stock': min_stock,
                'max_stock': max_stock
            }
            
            if db.update_inventory_item(product['id'], update_data):
                st.success("Product updated!")
                del st.session_state.edit_product
                time.sleep(1)
                st.rerun()
        
        if cancel_button:
            del st.session_state.edit_product
            st.rerun()

def add_product_form():
    """Form for adding new products"""
    with st.form("add_product_form", clear_on_submit=True):
        st.write("### Add New Product")
        
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Product Name*", key="add_name")
            description = st.text_area("Description", key="add_desc")
            
            # Category selection
            categories = db.get_categories()
            category_id = st.selectbox(
                "Category*",
                options=[c['id'] for c in categories],
                format_func=lambda x: next(c['name'] for c in categories if c['id'] == x),
                key="add_category"
            )
            
            # Subcategory selection
            subcategories = db.get_subcategories(category_id)
            subcategory_id = st.selectbox(
                "Subcategory",
                options=[sc['id'] for sc in subcategories],
                format_func=lambda x: next(sc['name'] for sc in subcategories if sc['id'] == x),
                key="add_subcategory"
            )
        
        with col2:
            price = st.number_input("Price*", min_value=0.0, step=0.01, key="add_price")
            cost = st.number_input("Cost", min_value=0.0, step=0.01, value=0.0, key="add_cost")
            quantity = st.number_input("Initial Quantity", min_value=0, value=0, key="add_qty")
            
            # Brand selection
            brands = db.get_brands()
            brand_id = st.selectbox(
                "Brand",
                options=[b['id'] for b in brands],
                format_func=lambda x: next(b['name'] for b in brands if b['id'] == x),
                key="add_brand"
            )
        
        # Barcode section
        barcode = st.text_input("Barcode", key="add_barcode")
        
        # Stock thresholds
        col3, col4 = st.columns(2)
        with col3:
            min_stock = st.number_input("Min Stock", min_value=0, value=5, key="add_min")
        with col4:
            max_stock = st.number_input("Max Stock", min_value=0, value=100, key="add_max")
        
        # Supplier selection
        suppliers = db.get_suppliers()
        supplier_id = st.selectbox(
            "Supplier",
            options=[s['id'] for s in suppliers],
            format_func=lambda x: next(s['name'] for s in suppliers if s['id'] == x),
            key="add_supplier"
        )
        
        # Image upload
        image_file = st.file_uploader("Product Image", type=["jpg", "jpeg", "png"], key="add_image")
        
        if st.form_submit_button("Add Product"):
            if not name or not price or not category_id:
                st.error("Please fill required fields (Name, Price, Category)")
            else:
                product_data = {
                    'name': name,
                    'description': description,
                    'price': price,
                    'cost': cost,
                    'quantity': quantity,
                    'barcode': barcode,
                    'category_id': category_id,
                    'subcategory_id': subcategory_id if subcategory_id else None,
                    'brand_id': brand_id if brand_id else None,
                    'supplier_id': supplier_id if supplier_id else None,
                    'min_stock': min_stock,
                    'max_stock': max_stock
                }
                
                if db.add_inventory_item(product_data):
                    # Handle image upload
                    if image_file:
                        os.makedirs("uploads/products", exist_ok=True)
                        file_ext = os.path.splitext(image_file.name)[1]
                        image_filename = f"product_{int(time.time())}{file_ext}"
                        image_path = os.path.join("uploads/products", image_filename)
                        
                        with open(image_path, "wb") as f:
                            f.write(image_file.getbuffer())
                        
                        # Update product with image path
                        db.update_inventory_item(product_data['id'], {'image_path': image_path})
                    
                    st.success("Product added successfully!")
                    time.sleep(1)
                    st.rerun()
# =============================================
# Category & Subcategory Management
# =============================================

def category_management():
    """Category and subcategory management interface"""
    if not check_permission("manage_categories"):
        st.warning("You don't have permission to access this section")
        return
    
    st.subheader("🏷️ Category Management")
    
    tab1, tab2 = st.tabs(["Categories", "Subcategories"])
    
    with tab1:
        st.write("### Product Categories")
        
        # Add new category
        with st.expander("Add New Category"):
            with st.form("add_category_form"):
                name = st.text_input("Category Name*", key="cat_name")
                description = st.text_input("Description", key="cat_desc")
                
                if st.form_submit_button("Add Category"):
                    if not name:
                        st.error("Category name is required")
                    else:
                        category_data = {
                            'name': name,
                            'description': description
                        }
                        
                        if db.add_category(category_data):
                            st.success("Category added successfully!")
                            time.sleep(1)
                            st.rerun()
        
        # List categories
        categories = db.get_categories()
        if categories:
            for category in categories:
                with st.expander(category['name']):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**Description:** {category.get('description', '')}")
                        st.write(f"**Created At:** {category['created_at']}")
                        
                        # Count products in this category
                        product_count = len([i for i in db.get_inventory_items() if i.get('category_id') == category['id']])
                        st.write(f"**Products:** {product_count}")
                    with col2:
                        # Edit category
                        with st.popover("Edit"):
                            with st.form(f"edit_category_{category['id']}"):
                                new_name = st.text_input(
                                    "Name", 
                                    value=category['name'],
                                    key=f"edit_cat_name_{category['id']}"
                                )
                                new_desc = st.text_input(
                                    "Description",
                                    value=category.get('description', ''),
                                    key=f"edit_cat_desc_{category['id']}"
                                )
                                
                                if st.form_submit_button("Update"):
                                    update_data = {
                                        'name': new_name,
                                        'description': new_desc
                                    }
                                    
                                    if db.update_category(category['id'], update_data):
                                        st.success("Category updated!")
                                        time.sleep(1)
                                        st.rerun()
                        
                        # Delete category (only if no products)
                        if product_count == 0:
                            if st.button("Delete", key=f"delete_cat_{category['id']}"):
                                success, message = db.delete_category(category['id'])
                                if success:
                                    st.success(message)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(message)
                        else:
                            st.info("Cannot delete - has products")
        else:
            st.info("No categories found")
    
    with tab2:
        st.write("### Product Subcategories")
        
        # Add new subcategory
        with st.expander("Add New Subcategory"):
            with st.form("add_subcategory_form"):
                col1, col2 = st.columns(2)
                with col1:
                    category_id = st.selectbox(
                        "Category*",
                        options=[c['id'] for c in db.get_categories()],
                        format_func=lambda x: next(c['name'] for c in db.get_categories() if c['id'] == x),
                        key="subcat_category"
                    )
                    name = st.text_input("Subcategory Name*", key="subcat_name")
                with col2:
                    description = st.text_input("Description", key="subcat_desc")
                
                if st.form_submit_button("Add Subcategory"):
                    if not name or not category_id:
                        st.error("Subcategory name and category are required")
                    else:
                        subcategory_data = {
                            'name': name,
                            'description': description,
                            'category_id': category_id
                        }
                        
                        if db.add_subcategory(subcategory_data):
                            st.success("Subcategory added successfully!")
                            time.sleep(1)
                            st.rerun()
        
        # List subcategories
        subcategories = db.get_subcategories()
        if subcategories:
            for subcategory in subcategories:
                with st.expander(f"{subcategory['name']} (under {next(c['name'] for c in db.get_categories() if c['id'] == subcategory['category_id'])})"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**Description:** {subcategory.get('description', '')}")
                        st.write(f"**Created At:** {subcategory['created_at']}")
                        
                        # Count products in this subcategory
                        product_count = len([i for i in db.get_inventory_items() if i.get('subcategory_id') == subcategory['id']])
                        st.write(f"**Products:** {product_count}")
                    with col2:
                        # Edit subcategory
                        with st.popover("Edit"):
                            with st.form(f"edit_subcat_{subcategory['id']}"):
                                new_name = st.text_input(
                                    "Name", 
                                    value=subcategory['name'],
                                    key=f"edit_subcat_name_{subcategory['id']}"
                                )
                                new_desc = st.text_input(
                                    "Description",
                                    value=subcategory.get('description', ''),
                                    key=f"edit_subcat_desc_{subcategory['id']}"
                                )
                                new_category = st.selectbox(
                                    "Category",
                                    options=[c['id'] for c in db.get_categories()],
                                    format_func=lambda x: next(c['name'] for c in db.get_categories() if c['id'] == x),
                                    index=next(i for i, c in enumerate(db.get_categories()) if c['id'] == subcategory['category_id']),
                                    key=f"edit_subcat_cat_{subcategory['id']}"
                                )
                                
                                if st.form_submit_button("Update"):
                                    update_data = {
                                        'name': new_name,
                                        'description': new_desc,
                                        'category_id': new_category
                                    }
                                    
                                    if db.update_subcategory(subcategory['id'], update_data):
                                        st.success("Subcategory updated!")
                                        time.sleep(1)
                                        st.rerun()
                        
                        # Delete subcategory (only if no products)
                        if product_count == 0:
                            if st.button("Delete", key=f"delete_subcat_{subcategory['id']}"):
                                success, message = db.delete_subcategory(subcategory['id'])
                                if success:
                                    st.success(message)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(message)
                        else:
                            st.info("Cannot delete - has products")
        else:
            st.info("No subcategories found")

# =============================================
# Brand & Location Management
# =============================================

def brand_location_management():
    """Brand and location management interface"""
    if not check_permission("manage_categories"):
        st.warning("You don't have permission to access this section")
        return
    
    st.subheader("🏢 Brand & Location Management")
    
    tab1, tab2 = st.tabs(["Brands", "Locations"])
    
    with tab1:
        st.write("### Product Brands")
        
        # Add new brand
        with st.expander("Add New Brand"):
            with st.form("add_brand_form"):
                name = st.text_input("Brand Name*", key="brand_name")
                description = st.text_input("Description", key="brand_desc")
                website = st.text_input("Website", key="brand_website")
                
                if st.form_submit_button("Add Brand"):
                    if not name:
                        st.error("Brand name is required")
                    else:
                        brand_data = {
                            'name': name,
                            'description': description,
                            'website': website
                        }
                        
                        if db.add_brand(brand_data):
                            st.success("Brand added successfully!")
                            time.sleep(1)
                            st.rerun()
        
        # List brands
        brands = db.get_brands()
        if brands:
            for brand in brands:
                with st.expander(brand['name']):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**Description:** {brand.get('description', '')}")
                        if brand.get('website'):
                            st.write(f"**Website:** [{brand['website']}]({brand['website']})")
                        st.write(f"**Created At:** {brand['created_at']}")
                        
                        # Count products for this brand
                        product_count = len([i for i in db.get_inventory_items() if i.get('brand_id') == brand['id']])
                        st.write(f"**Products:** {product_count}")
                    with col2:
                        # Edit brand
                        with st.popover("Edit"):
                            with st.form(f"edit_brand_{brand['id']}"):
                                new_name = st.text_input(
                                    "Name", 
                                    value=brand['name'],
                                    key=f"edit_brand_name_{brand['id']}"
                                )
                                new_desc = st.text_input(
                                    "Description",
                                    value=brand.get('description', ''),
                                    key=f"edit_brand_desc_{brand['id']}"
                                )
                                new_website = st.text_input(
                                    "Website",
                                    value=brand.get('website', ''),
                                    key=f"edit_brand_web_{brand['id']}"
                                )
                                
                                if st.form_submit_button("Update"):
                                    update_data = {
                                        'name': new_name,
                                        'description': new_desc,
                                        'website': new_website
                                    }
                                    
                                    if db.update_brand(brand['id'], update_data):
                                        st.success("Brand updated!")
                                        time.sleep(1)
                                        st.rerun()
                        
                        # Delete brand (only if no products)
                        if product_count == 0:
                            if st.button("Delete", key=f"delete_brand_{brand['id']}"):
                                success, message = db.delete_brand(brand['id'])
                                if success:
                                    st.success(message)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(message)
                        else:
                            st.info("Cannot delete - has products")
        else:
            st.info("No brands found")
    
    with tab2:
        st.write("### Inventory Locations")
        
        # Add new location
        with st.expander("Add New Location"):
            with st.form("add_location_form"):
                name = st.text_input("Location Name*", key="loc_name")
                description = st.text_input("Description", key="loc_desc")
                address = st.text_input("Address", key="loc_address")
                
                if st.form_submit_button("Add Location"):
                    if not name:
                        st.error("Location name is required")
                    else:
                        location_data = {
                            'name': name,
                            'description': description,
                            'address': address
                        }
                        
                        if db.add_location(location_data):
                            st.success("Location added successfully!")
                            time.sleep(1)
                            st.rerun()
        
        # List locations
        locations = db.get_locations()
        if locations:
            for location in locations:
                with st.expander(location['name']):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**Description:** {location.get('description', '')}")
                        if location.get('address'):
                            st.write(f"**Address:** {location['address']}")
                        st.write(f"**Created At:** {location['created_at']}")
                        
                        # Count products at this location
                        product_count = len([i for i in db.get_inventory_items() if i.get('location_id') == location['id']])
                        st.write(f"**Products:** {product_count}")
                    with col2:
                        # Edit location
                        with st.popover("Edit"):
                            with st.form(f"edit_loc_{location['id']}"):
                                new_name = st.text_input(
                                    "Name", 
                                    value=location['name'],
                                    key=f"edit_loc_name_{location['id']}"
                                )
                                new_desc = st.text_input(
                                    "Description",
                                    value=location.get('description', ''),
                                    key=f"edit_loc_desc_{location['id']}"
                                )
                                new_address = st.text_input(
                                    "Address",
                                    value=location.get('address', ''),
                                    key=f"edit_loc_addr_{location['id']}"
                                )
                                
                                if st.form_submit_button("Update"):
                                    update_data = {
                                        'name': new_name,
                                        'description': new_desc,
                                        'address': new_address
                                    }
                                    
                                    if db.update_location(location['id'], update_data):
                                        st.success("Location updated!")
                                        time.sleep(1)
                                        st.rerun()
                        
                        # Delete location (only if no products)
                        if product_count == 0:
                            if st.button("Delete", key=f"delete_loc_{location['id']}"):
                                success, message = db.delete_location(location['id'])
                                if success:
                                    st.success(message)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(message)
                        else:
                            st.info("Cannot delete - has products")
        else:
            st.info("No locations found")

# =============================================
# Supplier & Customer Management
# =============================================

def supplier_customer_management():
    """Supplier and customer management interface"""
    if not check_permission("manage_customers"):
        st.warning("You don't have permission to access this section")
        return
    
    st.subheader("🤝 Supplier & Customer Management")
    
    tab1, tab2 = st.tabs(["Suppliers", "Customers"])
    
    with tab1:
        st.write("### Suppliers")
        
        # Add new supplier
        with st.expander("Add New Supplier"):
            with st.form("add_supplier_form"):
                col1, col2 = st.columns(2)
                with col1:
                    name = st.text_input("Supplier Name*", key="supp_name")
                    email = st.text_input("Email", key="supp_email")
                    phone = st.text_input("Phone", key="supp_phone")
                with col2:
                    address = st.text_area("Address", key="supp_address")
                    website = st.text_input("Website", key="supp_website")
                
                if st.form_submit_button("Add Supplier"):
                    if not name:
                        st.error("Supplier name is required")
                    else:
                        supplier_data = {
                            'name': name,
                            'email': email,
                            'phone': phone,
                            'address': address,
                            'website': website
                        }
                        
                        if db.add_supplier(supplier_data):
                            st.success("Supplier added successfully!")
                            time.sleep(1)
                            st.rerun()
        
        # List suppliers
        suppliers = db.get_suppliers()
        if suppliers:
            for supplier in suppliers:
                with st.expander(supplier['name']):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**Email:** {supplier.get('email', '')}")
                        st.write(f"**Phone:** {supplier.get('phone', '')}")
                        st.write(f"**Address:** {supplier.get('address', '')}")
                        if supplier.get('website'):
                            st.write(f"**Website:** [{supplier['website']}]({supplier['website']})")
                    with col2:
                        # Edit supplier
                        with st.popover("Edit"):
                            with st.form(f"edit_supp_{supplier['id']}"):
                                new_name = st.text_input(
                                    "Name", 
                                    value=supplier['name'],
                                    key=f"edit_supp_name_{supplier['id']}"
                                )
                                new_email = st.text_input(
                                    "Email",
                                    value=supplier.get('email', ''),
                                    key=f"edit_supp_email_{supplier['id']}"
                                )
                                new_phone = st.text_input(
                                    "Phone",
                                    value=supplier.get('phone', ''),
                                    key=f"edit_supp_phone_{supplier['id']}"
                                )
                                new_address = st.text_area(
                                    "Address",
                                    value=supplier.get('address', ''),
                                    key=f"edit_supp_addr_{supplier['id']}"
                                )
                                new_website = st.text_input(
                                    "Website",
                                    value=supplier.get('website', ''),
                                    key=f"edit_supp_web_{supplier['id']}"
                                )
                                
                                if st.form_submit_button("Update"):
                                    update_data = {
                                        'name': new_name,
                                        'email': new_email,
                                        'phone': new_phone,
                                        'address': new_address,
                                        'website': new_website
                                    }
                                    
                                    if db.update_supplier(supplier['id'], update_data):
                                        st.success("Supplier updated!")
                                        time.sleep(1)
                                        st.rerun()
                        
                        # Count products from this supplier
                        product_count = len([i for i in db.get_inventory_items() if i.get('supplier_id') == supplier['id']])
                        
                        # Delete supplier (only if no products)
                        if product_count == 0:
                            if st.button("Delete", key=f"delete_supp_{supplier['id']}"):
                                success, message = db.delete_supplier(supplier['id'])
                                if success:
                                    st.success(message)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(message)
                        else:
                            st.info(f"Cannot delete - supplies {product_count} products")
        else:
            st.info("No suppliers found")
    
    with tab2:
        st.write("### Customers")
        
        # Add new customer
        with st.expander("Add New Customer"):
            with st.form("add_customer_form"):
                col1, col2 = st.columns(2)
                with col1:
                    name = st.text_input("Customer Name*", key="cust_name")
                    email = st.text_input("Email", key="cust_email")
                    phone = st.text_input("Phone", key="cust_phone")
                with col2:
                    address = st.text_area("Address", key="cust_address")
                    tax_id = st.text_input("Tax ID", key="cust_tax_id")
                
                if st.form_submit_button("Add Customer"):
                    if not name:
                        st.error("Customer name is required")
                    else:
                        customer_data = {
                            'name': name,
                            'email': email,
                            'phone': phone,
                            'address': address,
                            'tax_id': tax_id
                        }
                        
                        if db.add_customer(customer_data):
                            st.success("Customer added successfully!")
                            time.sleep(1)
                            st.rerun()
        
        # List customers
        customers = db.get_customers()
        if customers:
            for customer in customers:
                with st.expander(customer['name']):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**Email:** {customer.get('email', '')}")
                        st.write(f"**Phone:** {customer.get('phone', '')}")
                        st.write(f"**Address:** {customer.get('address', '')}")
                        if customer.get('tax_id'):
                            st.write(f"**Tax ID:** {customer['tax_id']}")
                    with col2:
                        # Edit customer
                        with st.popover("Edit"):
                            with st.form(f"edit_cust_{customer['id']}"):
                                new_name = st.text_input(
                                    "Name", 
                                    value=customer['name'],
                                    key=f"edit_cust_name_{customer['id']}"
                                )
                                new_email = st.text_input(
                                    "Email",
                                    value=customer.get('email', ''),
                                    key=f"edit_cust_email_{customer['id']}"
                                )
                                new_phone = st.text_input(
                                    "Phone",
                                    value=customer.get('phone', ''),
                                    key=f"edit_cust_phone_{customer['id']}"
                                )
                                new_address = st.text_area(
                                    "Address",
                                    value=customer.get('address', ''),
                                    key=f"edit_cust_addr_{customer['id']}"
                                )
                                new_tax_id = st.text_input(
                                    "Tax ID",
                                    value=customer.get('tax_id', ''),
                                    key=f"edit_cust_tax_{customer['id']}"
                                )
                                
                                if st.form_submit_button("Update"):
                                    update_data = {
                                        'name': new_name,
                                        'email': new_email,
                                        'phone': new_phone,
                                        'address': new_address,
                                        'tax_id': new_tax_id
                                    }
                                    
                                    if db.update_customer(customer['id'], update_data):
                                        st.success("Customer updated!")
                                        time.sleep(1)
                                        st.rerun()
                        
                        # Count invoices for this customer
                        invoice_count = len([i for i in db.get_invoices() if i.get('customer_id') == customer['id']])
                        
                        # Delete customer (only if no invoices)
                        if invoice_count == 0:
                            if st.button("Delete", key=f"delete_cust_{customer['id']}"):
                                success, message = db.delete_customer(customer['id'])
                                if success:
                                    st.success(message)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(message)
                        else:
                            st.info(f"Cannot delete - has {invoice_count} invoices")
        else:
            st.info("No customers found")

# =============================================
# Invoice Management
# =============================================
# =============================================
# Invoice Management - Improved Remove Item Functionality
# =============================================
# First, add the missing method to the JSONDatabase class

# Now fix the invoice management form with proper submit button
# =============================================
# Invoice Management - Fixed Remove Item Functionality
# =============================================
def invoice_management():
    """Complete Invoice Management Module with proper remove item functionality"""
    if not check_permission("create_invoice"):
        st.warning("You don't have permission to access this section")
        return

    st.title("🧾 Invoice & Financial Management")
    
    # Initialize session states
    if 'invoice_items' not in st.session_state:
        st.session_state.invoice_items = []
    if 'transaction_items' not in st.session_state:
        st.session_state.transaction_items = []
    if 'remove_items' not in st.session_state:
        st.session_state.remove_items = []
    
    # Main tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "Create Invoice", 
        "Invoice List", 
        "Record Transactions", 
        "Financial Reports"
    ])
    
    # =============================================
    # TAB 1: CREATE INVOICE - FIXED REMOVE ITEM
    # =============================================
    with tab1:
        st.header("📝 Create New Invoice")
        
        # Display current items outside the form
        if st.session_state.invoice_items:
            st.write("#### Current Invoice Items")
            
            # Create a more detailed display with remove indicators
            for idx, item in enumerate(st.session_state.invoice_items):
                col1, col2, col3, col4, col5, col6 = st.columns([4, 1, 1, 1, 1, 1])
                
                with col1:
                    st.write(f"**{item['item_name']}**")
                
                with col2:
                    st.write(f"{item['quantity']}x")
                
                with col3:
                    st.write(f"${item['unit_price']:.2f}")
                
                with col4:
                    st.write(f"${item['discount']:.2f}")
                
                with col5:
                    st.write(f"${item['total_price']:.2f}")
                
                with col6:
                    # Mark item for removal (will be processed after form submission)
                    if st.checkbox("Remove", key=f"remove_{idx}", help="Mark this item for removal"):
                        if idx not in st.session_state.remove_items:
                            st.session_state.remove_items.append(idx)
                    else:
                        if idx in st.session_state.remove_items:
                            st.session_state.remove_items.remove(idx)
            
            # Process removal of marked items
            if st.session_state.remove_items and st.button("Remove Marked Items"):
                # Remove items in reverse order to avoid index issues
                for idx in sorted(st.session_state.remove_items, reverse=True):
                    st.session_state.invoice_items.pop(idx)
                st.session_state.remove_items = []
                st.rerun()
            
            st.markdown("---")
            
            # Calculate totals
            tax_rates = db.get_tax_rates()
            shipping_cost = 0.0  # Will be set in the form
            
            subtotal = sum(item['total_price'] for item in st.session_state.invoice_items)
            total_discount = sum(item['discount'] for item in st.session_state.invoice_items)
            tax_amount = subtotal * (next((tr['rate']/100 for tr in tax_rates if tr['id'] == st.session_state.get('tax_rate_id')), 0)) if st.session_state.get('tax_rate_id') else 0
            total = subtotal + tax_amount + shipping_cost
            
            # Display totals in a clean format
            totals_col1, totals_col2 = st.columns(2)
            with totals_col1:
                st.metric("Subtotal", f"${subtotal:.2f}")
                st.metric("Total Discount", f"${total_discount:.2f}")
            with totals_col2:
                st.metric("Tax Amount", f"${tax_amount:.2f}")
                st.metric("Shipping", f"${shipping_cost:.2f}")
            
            st.success(f"**Grand Total: ${total:.2f}**")
        
        # Main invoice form
        with st.form("invoice_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            
            # Customer and Dates
            with col1:
                customers = db.get_customers()
                customer_id = st.selectbox(
                    "Customer*",
                    options=[c['id'] for c in customers],
                    format_func=lambda x: next(
                        (c['name'] for c in customers if c['id'] == x), 
                        "Select Customer"
                    ),
                    key="inv_customer"
                )
                
                invoice_date = st.date_input(
                    "Invoice Date*", 
                    value=datetime.date.today(),
                    key="inv_date"
                )
                due_date = st.date_input(
                    "Due Date*", 
                    value=datetime.date.today() + datetime.timedelta(days=30),
                    key="inv_due_date"
                )
                
                payment_terms = st.selectbox(
                    "Payment Terms*", 
                    ["Due on receipt", "Net 15", "Net 30", "Net 60"],
                    key="inv_payment_terms"
                )
            
            # Financial Details
            with col2:
                shipping_cost = st.number_input(
                    "Shipping Cost", 
                    min_value=0.0, 
                    value=0.0, 
                    step=0.01,
                    key="inv_shipping"
                )
                
                tax_rates = db.get_tax_rates()
                tax_rate_id = st.selectbox(
                    "Tax Rate",
                    options=[tr['id'] for tr in tax_rates],
                    format_func=lambda x: (
                        f"{next((tr['name'] for tr in tax_rates if tr['id'] == x), 'No Tax')} "
                        f"({next((tr['rate'] for tr in tax_rates if tr['id'] == x), 0)}%)"
                    ),
                    key="inv_tax_rate"
                ) if tax_rates else None
                
                notes = st.text_area(
                    "Notes", 
                    placeholder="Additional notes...",
                    key="inv_notes"
                )
            
            # Store tax_rate_id in session state for calculations
            if tax_rate_id:
                st.session_state.tax_rate_id = tax_rate_id
            
            # Invoice Items - Add new items
            st.subheader("Add New Item")
            inventory_items = db.get_inventory_items()
            
            if not inventory_items:
                st.error("No products available in inventory")
            else:
                item_col1, item_col2, item_col3, item_col4 = st.columns(4)
                
                with item_col1:
                    product_id = st.selectbox(
                        "Product*",
                        options=[i['id'] for i in inventory_items],
                        format_func=lambda x: (
                            f"{next((i['name'] for i in inventory_items if i['id'] == x), 'Unknown')} "
                            f"(Stock: {next((i['quantity'] for i in inventory_items if i['id'] == x), 0)})"
                        ),
                        key="inv_item_product"
                    )
                
                with item_col2:
                    max_qty = next(
                        (i['quantity'] for i in inventory_items if i['id'] == product_id),
                        0
                    )
                    quantity = st.number_input(
                        "Quantity*",
                        min_value=1,
                        max_value=max_qty,
                        value=min(1, max_qty),
                        key="inv_item_qty"
                    )
                
                with item_col3:
                    default_price = next(
                        (float(i['price']) for i in inventory_items if i['id'] == product_id),
                        0.01
                    )
                    unit_price = st.number_input(
                        "Unit Price*",
                        min_value=0.01,
                        value=default_price,
                        step=0.01,
                        key="inv_item_price"
                    )
                
                with item_col4:
                    discount = st.number_input(
                        "Discount",
                        min_value=0.0,
                        value=0.0,
                        step=0.01,
                        key="inv_item_discount"
                    )
                
                # Use st.form_submit_button for the add item button
                add_item_button = st.form_submit_button("Add Item to Invoice")
                
                if add_item_button:
                    product = next(
                        (i for i in inventory_items if i['id'] == product_id),
                        None
                    )
                    if product:
                        new_item = {
                            'item_id': product_id,
                            'item_name': product['name'],
                            'quantity': quantity,
                            'unit_price': unit_price,
                            'discount': discount,
                            'total_price': (unit_price * quantity) - discount
                        }
                        st.session_state.invoice_items.append(new_item)
                        st.rerun()
            
            # Final submission - Use st.form_submit_button for the main form
            submit_button = st.form_submit_button("Create Invoice", type="primary")
            
            if submit_button:
                if not st.session_state.invoice_items:
                    st.error("Please add at least one item")
                elif not customer_id:
                    st.error("Please select a customer")
                else:
                    # Recalculate totals with actual shipping cost
                    subtotal = sum(item['total_price'] for item in st.session_state.invoice_items)
                    total_discount = sum(item['discount'] for item in st.session_state.invoice_items)
                    tax_amount = subtotal * (next((tr['rate']/100 for tr in tax_rates if tr['id'] == tax_rate_id), 0)) if tax_rate_id else 0
                    total = subtotal + tax_amount + shipping_cost
                    
                    invoice_data = {
                        'customer_id': customer_id,
                        'date': invoice_date.isoformat(),
                        'due_date': due_date.isoformat(),
                        'payment_terms': payment_terms,
                        'shipping_cost': shipping_cost,
                        'tax_rate_id': tax_rate_id,
                        'tax_amount': tax_amount,
                        'subtotal': subtotal,
                        'discount': total_discount,
                        'total_amount': total,
                        'notes': notes,
                        'status': 'pending',
                        'amount_paid': 0.0,
                        'balance': total
                    }
                    
                    invoice_id = db.add_invoice(invoice_data)
                    if invoice_id:
                        for item in st.session_state.invoice_items:
                            db.add_invoice_item({
                                'invoice_id': invoice_id,
                                'item_id': item['item_id'],
                                'item_name': item['item_name'],
                                'quantity': item['quantity'],
                                'unit_price': item['unit_price'],
                                'discount': item['discount'],
                                'total_price': item['total_price']
                            })
                            
                            # Update inventory
                            product = db.get_inventory_item(item['item_id'])
                            if product:
                                new_qty = product['quantity'] - item['quantity']
                                db.update_inventory_item(item['item_id'], {'quantity': max(0, new_qty)})
                        
                        # Clear session state
                        st.session_state.invoice_items = []
                        st.session_state.remove_items = []
                        if 'tax_rate_id' in st.session_state:
                            del st.session_state.tax_rate_id
                        
                        st.success("Invoice created successfully!")
                        st.session_state.last_invoice_id = invoice_id
                        time.sleep(1)
                        st.rerun()

        # PDF download outside form
        if 'last_invoice_id' in st.session_state:
            invoice = db.get_invoice(st.session_state.last_invoice_id)
            if invoice and 'invoice_number' in invoice:
                pdf_path = generate_invoice_pdf(invoice['invoice_number'])
                if pdf_path:
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            "Download Invoice PDF",
                            f.read(),
                            file_name=f"{invoice['invoice_number']}.pdf",
                            mime="application/pdf"
                        )
    
    # [Rest of the tabs remain the same as before...]
    
    # =============================================
    # TAB 2: INVOICE LIST
    # =============================================
    with tab2:
        st.header("📋 Invoice List")
        
        # Filter options
        with st.expander("Filter Options", expanded=True):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                status_filter = st.selectbox(
                    "Status",
                    options=["All", "Pending", "Paid", "Partially Paid", "Cancelled"],
                    key="inv_filter_status"
                )
            
            with col2:
                customers = db.get_customers()
                customer_filter = st.selectbox(
                    "Customer",
                    options=["All"] + [c['name'] for c in customers],
                    key="inv_filter_customer"
                )
            
            with col3:
                date_range = st.selectbox(
                    "Date Range",
                    options=["All Time", "Last 7 Days", "Last 30 Days", "Last 90 Days", "Custom"],
                    key="inv_filter_date_range"
                )
            
            if date_range == "Custom":
                col4, col5 = st.columns(2)
                with col4:
                    custom_start = st.date_input(
                        "From",
                        value=datetime.date.today() - datetime.timedelta(days=30),
                        key="inv_filter_custom_start"
                    )
                with col5:
                    custom_end = st.date_input(
                        "To",
                        value=datetime.date.today(),
                        key="inv_filter_custom_end"
                    )
        
        # Apply filters
        invoices = db.get_invoices()
        
        if status_filter != "All":
            status_map = {
                "Pending": "pending",
                "Paid": "paid",
                "Partially Paid": "partially_paid",
                "Cancelled": "cancelled"
            }
            invoices = [i for i in invoices if i.get('status') == status_map[status_filter]]
        
        if customer_filter != "All":
            customer_id = next((c['id'] for c in customers if c['name'] == customer_filter), None)
            invoices = [i for i in invoices if i.get('customer_id') == customer_id]
        
        if date_range != "All Time":
            today = datetime.date.today()
            if date_range == "Last 7 Days":
                start_date = today - datetime.timedelta(days=7)
            elif date_range == "Last 30 Days":
                start_date = today - datetime.timedelta(days=30)
            elif date_range == "Last 90 Days":
                start_date = today - datetime.timedelta(days=90)
            else:  # Custom
                start_date = custom_start
                end_date = custom_end
            
            invoices = [
                i for i in invoices 
                if datetime.date.fromisoformat(i.get('date')) >= start_date
                and datetime.date.fromisoformat(i.get('date')) <= (end_date if date_range == "Custom" else today)
            ]
        
        # Display invoices
        if invoices:
            for invoice in invoices:
                total = invoice.get('total_amount', 0)
                paid = invoice.get('amount_paid', 0)
                balance = invoice.get('balance', total - paid)
                status = invoice.get('status', 'unknown').capitalize().replace('_', ' ')
                
                with st.expander(f"Invoice #{invoice.get('invoice_number', 'N/A')} - {status}"):
                    customer = db.get_customer(invoice.get('customer_id'))
                    
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write(f"**Customer:** {customer['name'] if customer else 'Walk-in'}")
                        st.write(f"**Date:** {invoice.get('date')}")
                        st.write(f"**Due Date:** {invoice.get('due_date')}")
                        st.write(f"**Total:** ${total:.2f}")
                        st.write(f"**Paid:** ${paid:.2f}")
                        st.write(f"**Balance:** ${balance:.2f}")
                        
                        if invoice.get('notes'):
                            st.write(f"**Notes:** {invoice['notes']}")
                    
                    with col2:
                        # View items
                        if st.button("📋 Details", key=f"view_{invoice['id']}"):
                            items = db.get_invoice_items(invoice['id'])
                            if items:
                                st.write("##### Invoice Items")
                                st.table([{
                                    'Product': item['item_name'],
                                    'Qty': item['quantity'],
                                    'Price': f"${item['unit_price']:.2f}",
                                    'Discount': f"${item['discount']:.2f}",
                                    'Total': f"${item['total_price']:.2f}"
                                } for item in items])
                            else:
                                st.info("No items found")
                        
                        # Payment handling
                        if balance > 0.01:
                            with st.popover("💳 Record Payment"):
                                with st.form(f"payment_{invoice['id']}"):
                                    amount = st.number_input(
                                        "Amount",
                                        min_value=0.01,
                                        max_value=float(balance),
                                        value=min(float(balance), 1000.0),
                                        step=0.01,
                                        key=f"pay_amount_{invoice['id']}"
                                    )
                                    method = st.selectbox(
                                        "Method",
                                        ["Cash", "Check", "Credit Card", "Bank Transfer"],
                                        key=f"pay_method_{invoice['id']}"
                                    )
                                    notes = st.text_area(
                                        "Notes",
                                        key=f"pay_notes_{invoice['id']}"
                                    )
                                    
                                    if st.form_submit_button("Submit Payment"):
                                        new_paid = paid + amount
                                        new_balance = max(0, total - new_paid)
                                        new_status = 'paid' if new_balance <= 0.01 else 'partially_paid'
                                        
                                        db.update_invoice(invoice['id'], {
                                            'amount_paid': new_paid,
                                            'balance': new_balance,
                                            'status': new_status
                                        })
                                        
                                        db.add_payment({
                                            'invoice_id': invoice['id'],
                                            'amount': amount,
                                            'method': method,
                                            'date': datetime.date.today().isoformat(),
                                            'notes': notes
                                        })
                                        
                                        st.success("Payment recorded!")
                                        time.sleep(1)
                                        st.rerun()
                        
                        # PDF download
                        if st.button("📄 PDF", key=f"pdf_{invoice['id']}"):
                            if 'invoice_number' in invoice:
                                pdf_path = generate_invoice_pdf(invoice['invoice_number'])
                                if pdf_path:
                                    with open(pdf_path, "rb") as f:
                                        st.download_button(
                                            "Download PDF",
                                            f.read(),
                                            file_name=f"{invoice['invoice_number']}.pdf",
                                            mime="application/pdf"
                                        )
                        
                        # Cancel invoice
                        if invoice['status'] != 'cancelled' and st.button("❌ Cancel", key=f"cancel_{invoice['id']}"):
                            db.update_invoice(invoice['id'], {'status': 'cancelled'})
                            st.success("Invoice cancelled")
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("No invoices found matching filters")
    
    # =============================================
    # TAB 3: RECORD TRANSACTIONS
    # =============================================
    with tab3:
        st.header("💸 Record Financial Transactions")
        
        with st.form("transaction_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                transaction_type = st.selectbox(
                    "Transaction Type*",
                    ["Expense", "Income", "Supplier Payment", "Other"],
                    key="trans_type"
                )
                
                category = st.selectbox(
                    "Category*",
                    ["Rent", "Transport", "Utilities", "Salaries", "Inventory Purchase", "Other"],
                    key="trans_category"
                )
                
                amount = st.number_input(
                    "Amount*",
                    min_value=0.01,
                    value=0.01,
                    step=0.01,
                    key="trans_amount"
                )
            
            with col2:
                supplier_id = None
                suppliers = db.get_suppliers()
                if transaction_type in ["Supplier Payment", "Inventory Purchase"]:
                    supplier_id = st.selectbox(
                        "Supplier",
                        [s['id'] for s in suppliers],
                        format_func=lambda x: next(
                            (s['name'] for s in suppliers if s['id'] == x), 
                            "Select Supplier"
                        ),
                        key="trans_supplier"
                    )
                
                date = st.date_input(
                    "Date*",
                    value=datetime.date.today(),
                    key="trans_date"
                )
                
                description = st.text_area(
                    "Description",
                    placeholder="Transaction details...",
                    key="trans_desc"
                )
            
            if st.form_submit_button("Add Transaction"):
                transaction_data = {
                    'type': transaction_type.lower(),
                    'category': category,
                    'amount': amount,
                    'date': date.isoformat(),
                    'description': description,
                    'supplier_id': supplier_id if supplier_id else None
                }
                
                if db.add_transaction(transaction_data):
                    st.success("Transaction recorded!")
                    time.sleep(1)
                    st.rerun()
    
    # =============================================
    # TAB 4: FINANCIAL REPORTS
    # =============================================
    with tab4:
        st.header("📊 Financial Reports")
        
        # Date range selection
        col1, col2 = st.columns(2)
        with col1:
            report_start = st.date_input(
                "Start Date", 
                value=datetime.date.today().replace(day=1),
                key="report_start"
            )
        with col2:
            report_end = st.date_input(
                "End Date", 
                value=datetime.date.today(),
                key="report_end"
            )
        
        # Report type selection
        report_type = st.radio(
            "Report Type",
            ["Profit & Loss", "Customer Debts", "Supplier Debts", "Transaction Records", "Comprehensive Report"],
            horizontal=True,
            key="report_type"
        )
        
        if st.button("Generate Report"):
            with st.spinner("Generating report..."):
                # Common data collection
                invoices = [
                    i for i in db.get_invoices()
                    if datetime.date.fromisoformat(i.get('date')) >= report_start
                    and datetime.date.fromisoformat(i.get('date')) <= report_end
                ]
                
                transactions = [
                    t for t in db.get_transactions()
                    if datetime.date.fromisoformat(t.get('date')) >= report_start
                    and datetime.date.fromisoformat(t.get('date')) <= report_end
                ]
                
                payments = [
                    p for p in db.get_payments()
                    if datetime.date.fromisoformat(p.get('date')) >= report_start
                    and datetime.date.fromisoformat(p.get('date')) <= report_end
                ]
                
                # Profit & Loss Report
                if report_type == "Profit & Loss":
                    st.subheader("💰 Profit & Loss Statement")
                    
                    # Revenue
                    total_revenue = sum(i['total_amount'] for i in invoices)
                    st.write(f"#### Revenue: ${total_revenue:,.2f}")
                    
                    # Expenses
                    expense_categories = {}
                    for t in transactions:
                        if t['type'] == 'expense':
                            cat = t['category']
                            expense_categories[cat] = expense_categories.get(cat, 0) + t['amount']
                    
                    st.write("#### Expenses")
                    if expense_categories:
                        for cat, amount in expense_categories.items():
                            st.write(f"- {cat}: ${amount:,.2f}")
                        total_expenses = sum(expense_categories.values())
                        st.write(f"**Total Expenses:** ${total_expenses:,.2f}")
                        
                        # Net Profit
                        net_profit = total_revenue - total_expenses
                        st.write(f"#### Net Profit: ${net_profit:,.2f}")
                    else:
                        st.info("No expenses recorded")
                
                # Customer Debts Report
                elif report_type == "Customer Debts":
                    st.subheader("🧾 Customer Outstanding Balances")
                    
                    customer_debts = {}
                    for inv in invoices:
                        if inv['status'] in ['pending', 'partially_paid']:
                            customer = db.get_customer(inv['customer_id'])
                            name = customer['name'] if customer else 'Walk-in'
                            customer_debts[name] = customer_debts.get(name, 0) + inv['balance']
                    
                    if customer_debts:
                        for customer, balance in customer_debts.items():
                            st.write(f"- {customer}: ${balance:,.2f}")
                        st.write(f"**Total Outstanding:** ${sum(customer_debts.values()):,.2f}")
                    else:
                        st.success("All customer accounts are current")
                
                # Supplier Debts Report
                elif report_type == "Supplier Debts":
                    st.subheader("📦 Supplier Outstanding Balances")
                    
                    supplier_debts = {}
                    for t in transactions:
                        if t['type'] == 'inventory purchase' and t['supplier_id']:
                            supplier = db.get_supplier(t['supplier_id'])
                            name = supplier['name'] if supplier else 'Unknown'
                            supplier_debts[name] = supplier_debts.get(name, 0) + t['amount']
                    
                    # Deduct supplier payments
                    for t in transactions:
                        if t['type'] == 'supplier payment' and t['supplier_id']:
                            supplier = db.get_supplier(t['supplier_id'])
                            name = supplier['name'] if supplier else 'Unknown'
                            supplier_debts[name] = supplier_debts.get(name, 0) - t['amount']
                    
                    if supplier_debts:
                        for supplier, balance in supplier_debts.items():
                            if balance > 0:
                                st.write(f"- {supplier}: ${balance:,.2f}")
                        total_debt = sum(v for v in supplier_debts.values() if v > 0)
                        st.write(f"**Total Outstanding:** ${total_debt:,.2f}")
                    else:
                        st.info("No supplier debts recorded")
                
                # Transaction Records
                elif report_type == "Transaction Records":
                    st.subheader("📝 Transaction History")
                    
                    if transactions:
                        trans_df = pd.DataFrame([{
                            'Date': t['date'],
                            'Type': t['type'].capitalize(),
                            'Category': t['category'],
                            'Amount': t['amount'],
                            'Description': t['description'],
                            'Supplier': db.get_supplier(t['supplier_id'])['name'] if t['supplier_id'] else ''
                        } for t in transactions])
                        
                        st.dataframe(
                            trans_df,
                            column_config={
                                "Amount": st.column_config.NumberColumn(format="$%.2f")
                            },
                            hide_index=True,
                            use_container_width=True
                        )
                        
                        # Export button
                        csv = trans_df.to_csv(index=False)
                        st.download_button(
                            "Export as CSV",
                            csv,
                            file_name=f"transactions_{report_start}_{report_end}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("No transactions in selected period")
                
                # Comprehensive Report
                elif report_type == "Comprehensive Report":
                    st.subheader("📊 Comprehensive Financial Report")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Revenue Summary
                        st.write("#### Revenue Summary")
                        total_revenue = sum(i['total_amount'] for i in invoices)
                        st.write(f"- Total Sales: ${total_revenue:,.2f}")
                        
                        # Customer Debts
                        customer_debts = sum(
                            inv['balance'] for inv in invoices 
                            if inv['status'] in ['pending', 'partially_paid']
                        )
                        st.write(f"- Outstanding Receivables: ${customer_debts:,.2f}")
                    
                    with col2:
                        # Expense Summary
                        st.write("#### Expense Summary")
                        expenses = sum(
                            t['amount'] for t in transactions 
                            if t['type'] == 'expense'
                        )
                        st.write(f"- Total Expenses: ${expenses:,.2f}")
                        
                        # Supplier Debts
                        supplier_purchases = sum(
                            t['amount'] for t in transactions 
                            if t['type'] == 'inventory purchase'
                        )
                        supplier_payments = sum(
                            t['amount'] for t in transactions 
                            if t['type'] == 'supplier payment'
                        )
                        supplier_debt = supplier_purchases - supplier_payments
                        st.write(f"- Outstanding Payables: ${supplier_debt:,.2f}")
                    
                    # Net Profit Calculation
                    st.write("---")
                    net_profit = total_revenue - expenses
                    st.write(f"#### Net Profit: ${net_profit:,.2f}")
                    
                    # Key Metrics
                    st.write("#### Key Metrics")
                    col3, col4 = st.columns(2)
                    with col3:
                        st.metric("Gross Revenue", f"${total_revenue:,.2f}")
                        st.metric("Total Expenses", f"${expenses:,.2f}")
                    with col4:
                        st.metric("Customer Debts", f"${customer_debts:,.2f}")
                        st.metric("Supplier Debts", f"${supplier_debt:,.2f}")

# =============================================
# Main Application Layout
# =============================================

def main():
    """Main application layout and routing"""
    
    # Initialize session state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    # Show login form if not authenticated
    if not st.session_state.authenticated:
        login_form()
        return
    
    # Main application after login
    st.sidebar.title(f"📦 {db.get_setting('company_name', 'Inventory System')}")
    
    # User info in sidebar
    with st.sidebar:
        st.write(f"Welcome, **{st.session_state.current_user}** ({st.session_state.current_role})")
        if st.button("Logout", use_container_width=True):
            logout()
            st.rerun()
    
    # Navigation menu based on user role
    menu_options = []
    
    if st.session_state.current_role == "Admin":
        menu_options = [
            "Dashboard", "Inventory", "Categories", "Brands & Locations",
            "Suppliers & Customers", "Invoices", "Reports", "Barcode Scanner",
            "Unknown Products", "User Management", "System Settings"
        ]
    elif st.session_state.current_role == "Manager":
        menu_options = [
            "Dashboard", "Inventory", "Categories", "Brands & Locations",
            "Suppliers & Customers", "Invoices", "Reports", "Barcode Scanner",
            "Unknown Products"
        ]
    elif st.session_state.current_role == "Sales":
        menu_options = [
            "Dashboard", "Inventory", "Invoices", "Reports", "Barcode Scanner",
            "Customers"
        ]
    elif st.session_state.current_role == "Warehouse":
        menu_options = [
            "Dashboard", "Inventory", "Barcode Scanner", "Unknown Products",
            "Suppliers"
        ]
    
    with st.sidebar:
        selected = option_menu(
            menu_title="Main Menu",
            options=menu_options,
            icons=[
                "speedometer2", "box-seam", "tags", "building", 
                "people", "receipt", "bar-chart", "upc-scan",
                "question-circle", "person-gear", "gear"
            ][:len(menu_options)],
            menu_icon="list",
            default_index=0
        )
    
    # Page routing
    if selected == "Dashboard":
        st.title("📊 Dashboard")
        reports_and_analytics()  # Reusing the reports view as dashboard
    
    elif selected == "Inventory":
        st.title("📦 Inventory Management")
        inventory_dashboard()
    
    elif selected == "Categories":
        st.title("🏷️ Category Management")
        category_management()
    
    elif selected == "Brands & Locations":
        st.title("🏢 Brand & Location Management")
        brand_location_management()
    
    elif selected == "Suppliers & Customers":
        st.title("🤝 Supplier & Customer Management")
        supplier_customer_management()
    
    elif selected == "Invoices":
        st.title("🧾 Invoice Management")
        invoice_management()
    
    elif selected == "Reports":
        st.title("📊 Reports & Analytics")
        reports_and_analytics()
    
    elif selected == "Barcode Scanner":
        st.title("📷 Barcode Scanner")
        barcode_scanner()
    
    elif selected == "Unknown Products":
        st.title("❓ Unknown Products")
        unknown_products()
    
    elif selected == "User Management":
        st.title("👥 User Management")
        user_management()
    
    elif selected == "System Settings":
        st.title("⚙️ System Settings")
        system_settings()
    
    # Add footer
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Version:** 1.0.0")
    st.sidebar.markdown(f"**Last Login:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

if __name__ == "__main__":
    main()