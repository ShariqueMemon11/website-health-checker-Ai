import requests
import ssl
import socket
from urllib.parse import urlparse, urljoin
from datetime import datetime
import time
from bs4 import BeautifulSoup
import sys

# Configuration
CONFIG = {
    "REQUEST_TIMEOUT": 15,
    "HEAD_REQUEST_TIMEOUT": 8,
    "SSL_EXPIRY_THRESHOLD": 15,
    "MAX_LINKS_TO_CHECK": 20
}

# -------- 1. Validate URL --------
def validate_url(url):
    """Validate and normalize the URL."""
    if not url:
        raise ValueError("URL cannot be empty")
    
    # Add protocol if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    # Parse and validate URL structure
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")
    
    return url

# -------- 2. Check if site is reachable --------
def check_site_status(url):
    """Check if the site is reachable and get response metrics."""
    try:
        # Add proper headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        start_time = time.time()
        response = requests.get(url, timeout=CONFIG["REQUEST_TIMEOUT"], headers=headers, allow_redirects=True)
        load_time = time.time() - start_time
        
        return True, response.status_code, response.headers, load_time
    
    except requests.exceptions.RequestException as e:
        return False, str(e), {}, None

# -------- 3. Check SSL Certificate --------
def check_ssl_certificate(url):
    """Check SSL certificate validity and expiration."""
    try:
        parsed_url = urlparse(url)
        hostname = parsed_url.netloc
        
        # Handle cases where hostname includes port number
        if ':' in hostname:
            hostname = hostname.split(':')[0]
        
        context = ssl.create_default_context()
        
        with socket.create_connection((hostname, 443), timeout=CONFIG["REQUEST_TIMEOUT"]) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                
                # Check if certificate is valid and extract expiration date
                if cert:
                    expires_str = cert['notAfter']
                    expires = datetime.strptime(expires_str, '%b %d %H:%M:%S %Y %Z')
                    days_left = (expires - datetime.utcnow()).days
                    
                    return True, days_left
                else:
                    return False, None
    except (socket.gaierror, socket.timeout) as e:
        return False, None
    except ssl.SSLError as e:
        return False, None
    except Exception as e:
        return False, None

# -------- 4. Check for broken links --------
def find_broken_links(url):
    """Find broken links on the page."""
    broken = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        response = requests.get(url, timeout=CONFIG["REQUEST_TIMEOUT"], headers=headers)
        if not response.ok:
            return broken
            
        soup = BeautifulSoup(response.text, 'html.parser')
        links = set()
        
        # Collect all links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if not href.startswith('#') and not href.startswith('javascript:'):
                full_url = urljoin(url, href)
                # Only check links from the same domain
                if urlparse(full_url).netloc == urlparse(url).netloc:
                    links.add(full_url)
        
        # Limit the number of links we check
        links_to_check = list(links)[:CONFIG["MAX_LINKS_TO_CHECK"]]
        
        # Check each link
        for link in links_to_check:
            try:
                resp = requests.head(link, allow_redirects=True, timeout=CONFIG["HEAD_REQUEST_TIMEOUT"], 
                                    headers=headers)
                if resp.status_code >= 400:
                    broken.append(f"{link} (Status: {resp.status_code})")
            except requests.exceptions.RequestException:
                broken.append(f"{link} (Error: Connection failed)")
        
        return broken
    except Exception:
        return broken

# -------- 5. Check for mobile responsiveness --------
def check_mobile_responsiveness(url):
    """Check if the site appears to be mobile responsive."""
    headers = {
        'User-Agent': (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 13_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1"
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    }
    try:
        response = requests.get(url, headers=headers, timeout=CONFIG["REQUEST_TIMEOUT"])
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check for viewport meta tag
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        has_viewport = bool(viewport and ('width=device-width' in viewport.get('content', '').lower() or 
                                         'initial-scale' in viewport.get('content', '').lower()))
        
        # Check for media queries in style tags
        media_queries = False
        for style in soup.find_all('style'):
            if style.string and '@media' in style.string:
                media_queries = True
                break
                
        # Check for responsive frameworks
        frameworks = False
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href', '').lower()
            if any(fw in href for fw in ['bootstrap', 'foundation', 'materialize', 'bulma', 'tailwind']):
                frameworks = True
                break
        
        # Overall assessment
        responsive = has_viewport or media_queries or frameworks
        
        details = []
        if has_viewport:
            details.append("Has viewport meta tag")
        if media_queries:
            details.append("Uses media queries")
        if frameworks:
            details.append("Uses responsive framework")
            
        return responsive, details
    except Exception:
        return False, ["Error checking responsiveness"]

# -------- 6. Generate suggestions --------
def generate_suggestions(ssl_ok, days_left, broken, mobile_result, load_time):
    """Generate actionable suggestions based on test results."""
    mobile_friendly, mobile_details = mobile_result
    suggestions = []

    # SSL suggestions
    if not ssl_ok:
        suggestions.append("Install a valid SSL certificate using Let's Encrypt or a trusted CA")
    elif days_left is not None and days_left < CONFIG["SSL_EXPIRY_THRESHOLD"]:
        suggestions.append(f"Renew your SSL certificate soon. It expires in {days_left} days")

    # Broken links suggestions
    if broken:
        suggestions.append(f"Fix {len(broken)} broken links on your website")

    # Mobile responsiveness suggestions
    if not mobile_friendly:
        suggestions.append("Improve mobile responsiveness by adding a viewport meta tag")
        suggestions.append("Consider using responsive frameworks like Bootstrap or Tailwind CSS")

    # Performance suggestions
    if load_time and load_time > 3:
        suggestions.append(f"Optimize page load time (currently {load_time:.2f}s)")
        suggestions.append("Compress images and minify CSS/JavaScript files")
        suggestions.append("Consider using a CDN for static assets")

    return suggestions

# -------- 7. Main function --------
def run_website_test(url):
    """Run the complete website health check and display the results in terminal."""
    try:
        url = validate_url(url)
        print(f"\n📊 Starting health check for {url}...\n")

        results = {}
        
        # Check site status
        print("⏳ Checking site status...")
        results['status'] = check_site_status(url)
        reachable, status, headers, load_time = results['status']
        
        if reachable:
            print(f"✅ Site is reachable (Status: {status})")
            if load_time:
                print(f"⏱️ Load time: {load_time:.2f} seconds")
        else:
            print(f"❌ Site is not reachable: {status}")
            results['ssl'] = (False, None)
            results['broken_links'] = []
            results['mobile'] = (False, ["Site not reachable"])
        
        if reachable:
            # Check SSL certificate
            print("\n⏳ Checking SSL certificate...")
            results['ssl'] = check_ssl_certificate(url)
            ssl_ok, days_left = results['ssl']
            
            if ssl_ok:
                print(f"✅ SSL certificate is valid (Expires in: {days_left} days)")
            else:
                print("❌ Invalid or missing SSL certificate")
            
            # Find broken links
            print("\n⏳ Checking for broken links...")
            results['broken_links'] = find_broken_links(url)
            broken = results['broken_links']
            
            if not broken:
                print("✅ No broken links found")
            else:
                print(f"❌ Found {len(broken)} broken links:")
                for i, link in enumerate(broken[:5]):
                    print(f"   {i+1}. {link}")
                if len(broken) > 5:
                    print(f"   ... and {len(broken) - 5} more")
            
            # Check mobile responsiveness
            print("\n⏳ Checking mobile responsiveness...")
            results['mobile'] = check_mobile_responsiveness(url)
            mobile_friendly, mobile_details = results['mobile']
            
            if mobile_friendly:
                print(f"✅ Site appears to be mobile responsive ({', '.join(mobile_details)})")
            else:
                print("⚠️ Site may not be fully mobile responsive")
        
        # Generate suggestions
        ssl_ok, days_left = results['ssl']
        broken = results['broken_links']
        mobile_result = results['mobile']
        
        suggestions = generate_suggestions(ssl_ok, days_left, broken, mobile_result, load_time)
        results['suggestions'] = suggestions

        # Print recommendations
        print("\n📝 RECOMMENDATIONS:")
        if suggestions:
            for suggestion in suggestions:
                print(f"  • {suggestion}")
        else:
            print("  ✅ Your site is in excellent health. Keep it up!")

        print("\n✅ Health check completed!\n")

    except Exception as e:
        print(f"❌ An error occurred: {str(e)}")

from IPython.display import HTML, display
from google.colab import output
import ipywidgets as widgets

def run_check(b):
    url = url_input.value.strip()
    if url:
        output.clear()
        run_website_test(url)
    else:
        print("Please enter a valid URL")

# Create input widget
url_input = widgets.Text(
    value='',
    placeholder='Enter website URL (e.g., example.com)',
    description='Website:',
    disabled=False,
    layout={'width': '50%'}
)

# Create button widget
check_button = widgets.Button(
    description='Run Health Check',
    disabled=False,
    button_style='primary',
    tooltip='Click to run the health check',
    icon='check'
)

check_button.on_click(run_check)

# Display the widgets
display(url_input)
display(check_button)
