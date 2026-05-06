import json
import csv
import os
import datetime
import ijson
from colorama import init, Fore, Style
import tempfile
from decimal import Decimal
import re

# Initialize colorama
init(autoreset=True)

SSA_NAMES_FILE = os.path.join(os.getcwd(), 'data', 'unique_names_ssa.txt')

def load_first_names(file_path: str) -> set:
    """Load first names from SSA file."""
    names = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                name = line.strip().split(',')[0].upper()
                if name:
                    names.add(name)
    except FileNotFoundError:
        print(f"{Fore.RED}Warning: {SSA_NAMES_FILE} not found! Name validation skipped{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error loading names: {e}{Style.RESET_ALL}")
    return names

valid_first_names = load_first_names(SSA_NAMES_FILE)

def convert_decimals_to_float(data):
    """Recursively convert Decimal to float."""
    if isinstance(data, Decimal):
        return float(data)
    if isinstance(data, dict):
        return {key: convert_decimals_to_float(value) for key, value in data.items()}
    if isinstance(data, list):
        return [convert_decimals_to_float(item) for item in data]
    return data

def process_first_name(first_name: str, username: str) -> str:
    """Validate first name against SSA list."""
    if not first_name or not valid_first_names:
        return f"@{username}"

    clean_name = re.sub(r'[^a-zA-Z]', '', first_name).strip()
    if not clean_name:
        return f"@{username}"
    
    formatted_name = clean_name.capitalize()
    
    if formatted_name.upper() in valid_first_names:
        return formatted_name
    else:
        return f"@{username}"

def format_location_details(all_locations: list) -> tuple:
    """
    Format location data into separate columns for CSV.
    Returns: (location_names, coordinates, post_links)
    """
    if not all_locations:
        return ('', '', '')
    
    # Limit to top 5 unique locations
    locations = all_locations[:5]
    
    location_names = []
    coordinates = []
    post_links = []
    
    for loc in locations:
        if loc.get('name'):
            location_names.append(loc['name'])
            
            lat = loc.get('lat')
            lng = loc.get('lng')
            if lat and lng:
                coordinates.append(f"{lat},{lng}")
            else:
                coordinates.append('N/A')
            
            if loc.get('post_link'):
                post_links.append(loc['post_link'])
            else:
                post_links.append('N/A')
    
    # Join with pipe separator
    location_names_str = ' | '.join(location_names)
    coordinates_str = ' | '.join(coordinates)
    post_links_str = ' | '.join(post_links)
    
    return (location_names_str, coordinates_str, post_links_str)

def create_csv_from_analyzed_json_efficiently(analyzed_json_path: str, output_csv_path: str):
    """
    Convert analyzed.json to CSV with enhanced location data.
    Memory-efficient streaming with ijson.
    """
    print(f"{Fore.CYAN}Starting enhanced CSV conversion with location data...{Style.RESET_ALL}")

    try:
        # Step 1: Sort by engagement rate
        print(f"{Fore.CYAN}Sorting creators by engagement rate...{Style.RESET_ALL}")
        creators_to_sort = []
        with open(analyzed_json_path, 'rb') as json_file:
            creators = ijson.items(json_file, 'creators.item')
            for creator in creators:
                engagement_rate = creator.get('average_engagement_rate', 0)
                creators_to_sort.append({'engagement_rate': engagement_rate, 'creator_data': creator})

        creators_to_sort.sort(key=lambda x: x['engagement_rate'], reverse=True)

        # Step 2: Write to temp file
        temp_file_path = None
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, newline='', encoding='utf-8') as temp_file:
            temp_file_path = temp_file.name
            creators_data_for_dump = [convert_decimals_to_float(item['creator_data']) for item in creators_to_sort]
            json.dump(creators_data_for_dump, temp_file)
        
        # Step 3: Write CSV with location columns
        print(f"{Fore.CYAN}Writing data to CSV with location intelligence...{Style.RESET_ALL}")
        
        headers = [
            # explicit PK and user fields
            'pk', 'fbid_v2', 'account_type', 'media_count', 'total_clips_count', 'pronouns', 'other_urls',
            "email", "primary_social_link", "username", "first_name", "last_name", "creator_type",
            "address_city", "address_state", "address_country", "address_zip",
            "primary_location_name", "latitude", "longitude",
            "all_location_names", "all_location_coordinates", "all_location_post_links",
            "posts_with_location", "total_posts_scraped",
            "collaboration_status", "top_collaboration", "top_collaboration_brand_logo", "hashtags", "niche_primary",
            "niche_secondary", "follower_count", "creator_size", "age_group", "age",
            "gender", "phone_number", "profile_picture", "tiktok_link",
            "youtube_link", "x_link", "linktree_link", "other_social_media",
            "business_category", "mention", "street_address",
            "bio_data", "last_updated", "source", "total_posts_in_3_months",
            "average_er_in_3_months", "total_collaborations", "ugc_examples",
            "tier", "price_usd", "time_15_seconds", "time_30_seconds",
            "time_60_seconds", "time_1_to_5_minutes", "time_greater_than_5_minutes","latest_post_link","latest_post_date",
            "estimated_roi", "impressions_visibility", "scraped_date", "analyzed_date"
        ]
        
        for j in range(6):
            headers.append(f"post{j+1}_interaction_score")
            headers.append(f"post{j+1}_accessibility_caption")
            headers.append(f"post{j+1}_media_type")

        total_users = 0
        with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(headers)
            
            with open(temp_file_path, 'r', encoding='utf-8') as temp_json_file:
                creators_data = json.load(temp_json_file)
                for creator in creators_data:
                    total_users += 1
                    
                    # newly added PK and user-level fields (ensure alignment with headers)
                    pk = creator.get('pk', '')
                    fbid_v2 = creator.get('fbid_v2', '')
                    account_type_val = creator.get('account_type', '')
                    media_count_val = creator.get('media_count', '')
                    total_clips_count_val = creator.get('total_clips_count', '')
                    pronouns_val = creator.get('pronouns', '')
                    other_urls_val = creator.get('other_urls', '')

                    username = creator.get('username', '')
                    first_name_raw = creator.get('first_name', '')
                    processed_first_name = process_first_name(first_name_raw, username)
                    processed_last_name = ''
                    
                    email = creator.get('email', '')
                    
                    # Enhanced location fields
                    address_city = creator.get('address_city', '')
                    address_state = creator.get('address_state', '')
                    address_country = creator.get('address_country', '')
                    address_zip = creator.get('address_zip', '')
                    
                    # Primary location
                    primary_location_name = creator.get('primary_location_name', '')
                    latitude = creator.get('latitude', '')
                    longitude = creator.get('longitude', '')
                    
                    # All locations with details
                    all_locations = creator.get('all_locations', [])
                    location_names_str, coordinates_str, post_links_str = format_location_details(all_locations)
                    
                    posts_with_location = creator.get('posts_with_location', 0)
                    total_posts_scraped = creator.get('total_posts_scraped', 0)
                    
                    collaboration_status = creator.get('collaboration_status', '')
                    
                    top_collaboration_list = [
                        c.get('name') for c in creator.get('top_collaboration', [])
                        if c.get('source') in ['paid_partnership']
                    ]
                    top_collaboration_str = " | ".join(top_collaboration_list)
                    
                    top_collaboration_brand_logo_list = []
                    for collab in creator.get('top_collaboration', []):
                        if collab.get('source') in ['paid_partnership']:
                            brand_name = collab.get('name', '')
                            if brand_name:
                                logo_url = f"https://assets.veelapp.com/{brand_name.strip()}.jpg"
                                top_collaboration_brand_logo_list.append(f"{brand_name.strip()};{logo_url}")
                    top_collaboration_brand_logo = " | ".join(top_collaboration_brand_logo_list)

                    hashtags_dict = creator.get('hashtags_last_90_days', {})
                    hashtags_sorted = sorted(hashtags_dict.items(), key=lambda x: x[1], reverse=True)
                    hashtags_top = [tag for tag, count in hashtags_sorted[:10]] if len(hashtags_sorted) >= 10 else [tag for tag, count in hashtags_sorted[:5]]
                    hashtags_pipeline = " | ".join(hashtags_top)
                    
                    niche_primary = creator.get('niche_data', {}).get('overall_niche', '')
                    niche_secondary = ''
                    creator_type = creator.get('creator_type', '')
                    follower_count = creator.get('follower_count', 0)
                    creator_size = creator.get('creator_size', '')
                    age_group = ''
                    age = ''
                    gender = creator.get('gender', '')
                    phone_number = creator.get('phone_number', '')
                    profile_picture = creator.get('profile_picture', '')
                    
                    social_links = creator.get('social_links', {})
                    tiktok_link = social_links.get('tiktok', '')
                    youtube_link = social_links.get('youtube', '')
                    x_link = social_links.get('x', '')
                    linktree_link = social_links.get('linktree', '')
                    
                    other_social_media_list = [tiktok_link, youtube_link, x_link, linktree_link]
                    other_social_media = " | ".join(link for link in other_social_media_list if link)

                    primary_social_link = f"https://www.instagram.com/{username}" if username else ''
                    
                    business_category = creator.get('business_category', '')
                    mentions_dict = creator.get('mentions_last_90_days', {})
                    mentions_sorted = sorted(mentions_dict.items(), key=lambda x: x[1], reverse=True)
                    mentions_top = [m for m, c in mentions_sorted[:10]] if len(mentions_sorted) >= 10 else [m for m, c in mentions_sorted[:5]]
                    mentions_pipeline = " | ".join(mentions_top)

                    street_address = creator.get('street_address', '')
                    bio_data = creator.get('biography', '').replace('\n', ' ').replace(',', ' ')
                    last_updated = creator.get('analyzed_date', '')
                    source = creator.get('source', '')
                    total_posts_in_3_months = creator.get('total_posts_last_3_months', 0)
                    average_er_in_3_months = creator.get('average_engagement_rate', 0)
                    total_collaborations = creator.get('total_collaborations', 0)
                    ugc_examples = creator.get('ugc_examples', '')
                    latest_post_link = creator.get('latest_post_link', '')
                    latest_post_date = creator.get('latest_post_date','')

                    price_usd_list = []
                    creator_pricing_metrics = creator.get('creator_pricing_metrics', {})
                    if creator_pricing_metrics:
                        price_usd_list.append(f"TIME_15_SECONDS:{creator_pricing_metrics.get('time_15_seconds', '')}")
                        price_usd_list.append(f"TIME_30_SECONDS:{creator_pricing_metrics.get('time_30_seconds', '')}")
                        price_usd_list.append(f"TIME_60_SECONDS:{creator_pricing_metrics.get('time_60_seconds', '')}")
                        price_usd_list.append(f"TIME_1_TO_5_MINUTES:{creator_pricing_metrics.get('time_1_to_5_minutes', '')}")
                        price_usd_list.append(f"TIME_GREATER_THAN_5_MINUTES:{creator_pricing_metrics.get('time_greater_than_5_minutes', '')}")
                    price_usd = '|'.join(price_usd_list)

                    tier = creator.get('tier', '')
                    time_15_seconds = creator_pricing_metrics.get('time_15_seconds', '')
                    time_30_seconds = creator_pricing_metrics.get('time_30_seconds', '')
                    time_60_seconds = creator_pricing_metrics.get('time_60_seconds', '')
                    time_1_to_5_minutes = creator_pricing_metrics.get('time_1_to_5_minutes', '')
                    time_greater_than_5_minutes = creator_pricing_metrics.get('time_greater_than_5_minutes', '')
                    estimated_roi = creator_pricing_metrics.get('estimated_roi', '')
                    impressions_visibility = creator_pricing_metrics.get('impressions_visibility', '')
                    scraped_date = creator.get('scraped_date','')
                    analyzed_date = creator.get('analyzed_date', '')

                    row = [
                        pk, fbid_v2, account_type_val, media_count_val, total_clips_count_val, pronouns_val, other_urls_val,
                        email, primary_social_link, username, processed_first_name, processed_last_name, creator_type,
                        address_city, address_state, address_country, address_zip,
                        primary_location_name, latitude, longitude,
                        location_names_str, coordinates_str, post_links_str,
                        posts_with_location, total_posts_scraped,
                        collaboration_status, top_collaboration_str, top_collaboration_brand_logo, hashtags_pipeline,
                        niche_primary, niche_secondary, follower_count, creator_size,
                        age_group, age, gender, phone_number, profile_picture, tiktok_link,
                        youtube_link, x_link, linktree_link, other_social_media,
                        business_category, mentions_pipeline, street_address,
                        bio_data, last_updated, source,
                        total_posts_in_3_months, average_er_in_3_months,
                        total_collaborations, ugc_examples,
                        tier, price_usd, time_15_seconds, time_30_seconds,
                        time_60_seconds, time_1_to_5_minutes, time_greater_than_5_minutes,latest_post_link,latest_post_date,
                        estimated_roi, impressions_visibility, scraped_date, analyzed_date
                    ]
                    
                    top_posts = creator.get('top_6_posts', [])
                    for j in range(6):
                        if j < len(top_posts):
                            post = top_posts[j]
                            interaction_score = post.get('interaction_score', 0)
                            media_type = post.get('media_type', '')
                            accessibility_caption = post.get('accessibility_caption', '')
                            row.append(interaction_score)
                            row.append(accessibility_caption if accessibility_caption is not None else '')
                            row.append(media_type if media_type is not None else '')
                        else:
                            row.extend(['', '', ''])

                    cleaned_row = [str(item).replace(',', '') if isinstance(item, str) else item for item in row]
                    writer.writerow(cleaned_row)
        
        os.remove(temp_file_path)

        return True, total_users

    except Exception as e:
        print(f"{Fore.RED}Error processing JSON: {str(e)}{Style.RESET_ALL}")
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return False, 0

def main():
    """Main function with location data support."""
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Enhanced JSON to CSV Converter with Location Intelligence{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}\n")
    
    analyzed_json_file = os.path.join(os.getcwd(), 'data', 'analyzed.json')
    today_date = datetime.datetime.now().strftime('%Y%m%d')
    output_csv_file = os.path.join(os.getcwd(), 'data', f'output_{today_date}.csv')
    
    if not os.path.exists(analyzed_json_file):
        print(f"{Fore.RED}analyzed.json not found at {analyzed_json_file}!{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Run the analyzer script first (tools/finalanalyzer_full.py){Style.RESET_ALL}")
        return
    
    print(f"{Fore.GREEN}✓ Found analyzed.json{Style.RESET_ALL}")
    print(f"{Fore.GREEN}✓ Output: {output_csv_file}{Style.RESET_ALL}\n")
    
    try:
        with open(analyzed_json_file, 'rb') as json_file:
            parser = ijson.parse(json_file)
            analyzed_data_info = {}
            for prefix, event, value in parser:
                if prefix == 'analysis_date' and event == 'string':
                    analyzed_data_info['analysis_date'] = value
                if prefix == 'total_creators_analyzed' and event == 'number':
                    analyzed_data_info['total_creators_analyzed'] = int(value)
                if prefix == 'creators_with_location' and event == 'number':
                    analyzed_data_info['creators_with_location'] = int(value)
                if prefix == 'location_coverage_percentage' and event == 'number':
                    analyzed_data_info['location_coverage_percentage'] = float(value)
                if prefix == 'creators' and event == 'start_array':
                    break
            
            analysis_date = analyzed_data_info.get('analysis_date', 'Unknown')
            total_creators = analyzed_data_info.get('total_creators_analyzed', 0)
            creators_with_location = analyzed_data_info.get('creators_with_location', 0)
            location_percentage = analyzed_data_info.get('location_coverage_percentage', 0)
            
            print(f"{Fore.CYAN}Analysis Information:{Style.RESET_ALL}")
            print(f"  Date: {analysis_date}")
            print(f"  Total Creators: {total_creators}")
            print(f"  With Location: {creators_with_location} ({location_percentage}%)")
            print()
    except Exception as e:
        print(f"{Fore.RED}Error reading JSON metadata: {str(e)}{Style.RESET_ALL}")
        return
    
    success, total_users = create_csv_from_analyzed_json_efficiently(analyzed_json_file, output_csv_file)
    
    if success:
        print(f"\n{Fore.GREEN}{'='*70}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}✓ CSV created successfully: {output_csv_file}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}✓ Total users converted: {total_users}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*70}{Style.RESET_ALL}\n")
        
        print(f"{Fore.YELLOW}New Location Columns Added:{Style.RESET_ALL}")
        print(f"  • primary_location_name")
        print(f"  • latitude, longitude")
        print(f"  • all_location_names (pipe-separated)")
        print(f"  • all_location_coordinates (pipe-separated)")
        print(f"  • all_location_post_links (pipe-separated)")
        print(f"  • posts_with_location / total_posts_scraped")
        print(f"  • address_city, address_state, address_country")
        print()
        
    else:
        print(f"{Fore.RED}✗ Conversion failed!{Style.RESET_ALL}")

if __name__ == "__main__":
    main()