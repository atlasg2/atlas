import csv
import json
import os
import re
import datetime
from typing import Dict, List, Any, Optional, Set

def clean_string(s: Optional[str]) -> str:
    """Clean up strings and handle None values."""
    if s is None or s == "None" or s == "":
        return ""
    return str(s).strip()

def clean_number(n: Optional[str]) -> Optional[int]:
    """Convert string numbers to integers, handling None and empty values."""
    if n is None or n == "None" or n == "":
        return None
    try:
        return int(float(n))
    except (ValueError, TypeError):
        return None

def parse_hours(hours_string: str) -> Dict[str, str]:
    """Parse hours from different formats."""
    if not hours_string or hours_string == "None":
        return {}
    
    hours_obj = {}
    
    try:
        # Handle JSON-like format
        if hours_string.startswith("{"):
            # Replace single quotes with double quotes
            json_str = hours_string.replace("'", '"')
            hours_obj = json.loads(json_str)
            return hours_obj
        
        # Handle pipe-delimited format
        if "|" in hours_string:
            for day_hour in hours_string.split("|"):
                parts = day_hour.split(":")
                if len(parts) == 2:
                    day, time = parts
                    hours_obj[day.lower()] = time
            return hours_obj
        
        # If it's neither format, return as raw_hours
        return {"raw_hours": hours_string}
    except Exception:
        # If parsing fails, return the raw string
        return {"raw_hours": hours_string}

def convert_to_json(csv_file: str, output_file: str, specific_rows: List[int]) -> None:
    """Convert specific rows from CSV file to enhanced JSON structure and write to file."""
    current_year = datetime.datetime.now().year
    
    # Read CSV file
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)  # Get header row
        
        # Create header to index mapping
        header_map = {header: i for i, header in enumerate(headers)}
        
        # Prepare the JSON structure
        hvac_contractors = []
        
        # Read all rows into memory
        all_rows = list(reader)
        
        # Process only specific rows
        for row_index in specific_rows:
            # Adjust for 0-indexing and header row
            adjusted_index = row_index - 1
            
            if adjusted_index < 0 or adjusted_index >= len(all_rows):
                print(f"Warning: Row {row_index} is out of range")
                continue
                
            row = all_rows[adjusted_index]
            
            # Skip empty rows
            if not row or not row[header_map.get('name', 0)]:
                print(f"Warning: Row {row_index} is empty or has no name")
                continue
            
            # Helper function to get value from row safely
            def get_value(key, default=""):
                index = header_map.get(key)
                if index is None or index >= len(row):
                    return default
                return clean_string(row[index])
            
            # Helper function to get numeric value
            def get_number(key, default=None):
                val = get_value(key)
                if not val:
                    return default
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return default
            
            # Helper function for boolean values
            def get_boolean(key, default=False):
                val = get_value(key)
                return val.upper() == "TRUE" if val else default
            
            # Basic business information
            name = get_value('name')
            query = get_value('query')
            place_id = get_value('place_id')
            slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
            
            # Contact information
            phone = get_value('phone')
            phone_type = get_value('phone.phones_enricher.carrier_type')
            phone_carrier = get_value('phone.phones_enricher.carrier_name')
            
            # Location information
            city = get_value('city')
            state = get_value('state', get_value('us_state'))
            zip_code = get_value('postal_code')
            full_address = get_value('full_address')
            latitude = get_number('latitude')
            longitude = get_number('longitude')
            
            # Email information
            email1 = get_value('email_1')
            email1_status = get_value('email_1.emails_validator.status')
            email1_details = get_value('email_1.emails_validator.status_details')
            
            # Business details
            year_founded = clean_number(get_value('site.company_insights.founded_year', 
                                                 get_value('company_year_started')))
            employee_count = clean_number(get_value('site.company_insights.employees', 
                                                   get_value('number_of_employees')))
            description = get_value('description', get_value('site.company_insights.description'))
            
            # Verification status
            verified = get_boolean('verified')
            
            # Services
            services = []
            subtypes = get_value('subtypes')
            if subtypes:
                services = [s.strip() for s in subtypes.split(',') if s.strip()]
            
            # Parse hours
            hours_obj = parse_hours(get_value('working_hours'))
            
            # Process phone numbers to avoid duplicates
            additional_phones = []
            processed_phone_numbers = set()
            
            # Add main phone to processed set
            if phone:
                processed_phone_numbers.add(re.sub(r'\D', '', phone))
            
            # Add additional phones if not duplicates
            for phone_field in ['phone_1', 'phone_2', 'phone_3']:
                phone_number = get_value(phone_field)
                if phone_number:
                    clean_phone = re.sub(r'\D', '', phone_number)
                    
                    if clean_phone and clean_phone not in processed_phone_numbers:
                        processed_phone_numbers.add(clean_phone)
                        
                        additional_phones.append({
                            "number": phone_number,
                            "type": get_value(f'{phone_field}.phones_enricher.carrier_type'),
                            "carrier": get_value(f'{phone_field}.phones_enricher.carrier_name')
                        })
            
            # Process emails
            additional_emails = []
            
            # Add additional emails
            for email_field in ['email_2', 'email_3']:
                email = get_value(email_field)
                if email:
                    additional_emails.append({
                        "address": email,
                        "status": get_value(f'{email_field}.emails_validator.status'),
                        "validation_details": get_value(f'{email_field}.emails_validator.status_details'),
                        "contact": {
                            "full_name": get_value(f'{email_field}_full_name'),
                            "first_name": get_value(f'{email_field}_first_name'),
                            "last_name": get_value(f'{email_field}_last_name'),
                            "title": get_value(f'{email_field}_title')
                        }
                    })
            
            # Calculate years in business
            years_in_business = None
            if year_founded:
                years_in_business = current_year - int(year_founded)
            
            # Check if email is valid
            has_valid_email = email1_status == 'RECEIVING'
            
            # Check if phone is mobile
            has_mobile_phone = phone_type.lower() == 'mobile' or any(
                p["type"].lower() == 'mobile' for p in additional_phones if p["type"])
            
            website = get_value('site')
            facebook = get_value('facebook')
            rating = get_number('rating')
            reviews_count = clean_number(get_value('reviews'))
            photos_count = clean_number(get_value('photos_count', 0))
            
            # Build the contractor object
            contractor = {
                "id": place_id or f"id-{row_index}-{int(datetime.datetime.now().timestamp())}",
                "slug": slug,
                "basic_info": {
                    "name": name,
                    "query": query,
                    "location": {
                        "city": city,
                        "state": state,
                        "zip": zip_code,
                        "full_address": full_address,
                        "latitude": latitude,
                        "longitude": longitude
                    }
                },
                "contact_info": {
                    "phone": {
                        "primary": phone,
                        "type": phone_type,
                        "carrier": phone_carrier,
                        "additional_phones": additional_phones
                    },
                    "email": {
                        "address": email1,
                        "status": email1_status,
                        "validation_details": email1_details,
                        "contact": {
                            "full_name": get_value('email_1_full_name'),
                            "first_name": get_value('email_1_first_name'),
                            "last_name": get_value('email_1_last_name'),
                            "title": get_value('email_1_title')
                        }
                    },
                    "additional_emails": additional_emails
                },
                "web_presence": {
                    "website": website,
                    "website_details": {
                        "has_website": bool(website),
                        "title": get_value('website_title'),
                        "description": get_value('website_description'),
                        "generator": get_value('website_generator'),
                        "has_fb_pixel": get_boolean('website_has_fb_pixel'),
                        "has_google_tag": get_boolean('website_has_google_tag')
                    },
                    "social_media": {
                        "facebook": facebook,
                        "instagram": get_value('instagram'),
                        "linkedin": get_value('linkedin'),
                        "twitter": get_value('twitter'),
                        "youtube": get_value('youtube')
                    }
                },
                "business_details": {
                    "year_founded": year_founded,
                    "years_in_business": years_in_business,
                    "employee_count": employee_count,
                    "business_type": get_value('business_type'),
                    "description": description,
                    "services": services,
                    "hours": hours_obj
                },
                "online_presence": {
                    "google_rating": rating,
                    "google_reviews_count": reviews_count,
                    "google_reviews_link": get_value('reviews_link'),
                    "google_place_id": place_id,
                    "business_status": get_value('business_status'),
                    "photos_count": photos_count,
                    "photo_url": get_value('photo'),
                    "verified": verified
                },
                "segmentation": {
                    "has_valid_email": has_valid_email,
                    "has_mobile_phone": has_mobile_phone,
                    "has_website": bool(website),
                    "has_facebook": bool(facebook),
                    "has_reviews": bool(reviews_count and reviews_count > 0),
                    "high_rating": bool(rating and rating >= 4.5),
                    "established_business": bool(years_in_business and years_in_business > 5),
                    "is_verified": verified
                }
            }
            
            hvac_contractors.append(contractor)
            print(f"Processed row {row_index}: {name}")
        
        # Generate segment stats
        segments = {
            "with_website": len([c for c in hvac_contractors if c["segmentation"]["has_website"]]),
            "with_valid_email": len([c for c in hvac_contractors if c["segmentation"]["has_valid_email"]]),
            "with_mobile_phone": len([c for c in hvac_contractors if c["segmentation"]["has_mobile_phone"]]),
            "high_rated": len([c for c in hvac_contractors if c["segmentation"]["high_rating"]]),
            "established": len([c for c in hvac_contractors if c["segmentation"]["established_business"]]),
            "verified": len([c for c in hvac_contractors if c["segmentation"]["is_verified"]])
        }
        
        # Create the final JSON object
        json_data = {
            "hvac_contractors": hvac_contractors,
            "meta": {
                "total_count": len(hvac_contractors),
                "generated_at": datetime.datetime.now().isoformat(),
                "segments": segments,
                "processed_rows": specific_rows
            }
        }
        
        # Write to JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        print(f"Processed {len(hvac_contractors)} businesses to {output_file}")
        print(f"Segment stats: {segments}")

if __name__ == "__main__":
    input_file = "Untitled spreadsheet - Outscraper-20250408050716s6d_hvac_contractor (3).csv"
    output_file = "hvac_contractors_selected_rows.json"
    
    # Process only these specific rows
    specific_rows = [5, 6, 29, 30, 35, 36, 42]
    
    convert_to_json(input_file, output_file, specific_rows)
