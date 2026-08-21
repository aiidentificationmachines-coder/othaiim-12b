#!/usr/bin/env python3
"""
Solas Web Search — Local DGX Edition
Searches the internet from the DGX Spark without cloud credits.
Uses DuckDuckGo HTML API (free, no key needed) + Wikipedia API.

Capabilities:
- Web search via DuckDuckGo
- Wikipedia lookups
- News search
- Result summarization
"""

import json, os, sys, re, urllib.request, urllib.parse, html
from datetime import datetime, timezone

def search_ddg(query, max_results=10):
    """Search DuckDuckGo HTML version (free, no API key needed)."""
    query_encoded = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={query_encoded}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        resp = urllib.request.urlopen(req, timeout=15)
        html_content = resp.read().decode("utf-8", errors="ignore")
        
        results = []
        # Parse DuckDuckGo HTML results
        # Results are in <a class="result__a" href="...">title</a>
        # Snippets in <a class="result__snippet" ...>text</a>
        
        result_links = re.findall(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html_content, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|span)', html_content, re.DOTALL)
        
        for i, (link, title) in enumerate(result_links[:max_results]):
            # Clean title
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            title_clean = html.unescape(title_clean)
            
            # Decode DDG redirect URLs
            if "uddg=" in link:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                if "uddg" in parsed:
                    link = parsed["uddg"][0]
            
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                snippet = html.unescape(snippet)
            
            results.append({
                "title": title_clean,
                "url": link,
                "snippet": snippet[:300],
            })
        
        return results
    except Exception as e:
        return [{"error": str(e)}]

def search_wikipedia(query, max_results=5):
    """Search Wikipedia API (free, no key needed)."""
    query_encoded = urllib.parse.quote(query)
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query_encoded}&format=json&srlimit={max_results}"
    
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Solas-DGX-Bot/1.0")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        
        results = []
        for item in data.get("query", {}).get("search", []):
            results.append({
                "title": item.get("title", ""),
                "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(item.get('title', '').replace(' ', '_'))}",
                "snippet": re.sub(r'<[^>]+>', '', item.get("snippet", ""))[:300],
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]

def get_wikipedia_summary(title):
    """Get a Wikipedia article summary."""
    title_encoded = urllib.parse.quote(title)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title_encoded}"
    
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Solas-DGX-Bot/1.0")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return {
            "title": data.get("title", ""),
            "extract": data.get("extract", ""),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        }
    except Exception as e:
        return {"error": str(e)}

def search_news(query, max_results=10):
    """Search for recent news. Uses DuckDuckGo news."""
    query_encoded = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={query_encoded}&iar=news"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        resp = urllib.request.urlopen(req, timeout=15)
        html_content = resp.read().decode("utf-8", errors="ignore")
        
        result_links = re.findall(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html_content, re.DOTALL)
        
        results = []
        for link, title in result_links[:max_results]:
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            title_clean = html.unescape(title_clean)
            if "uddg=" in link:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                if "uddg" in parsed:
                    link = parsed["uddg"][0]
            results.append({"title": title_clean, "url": link})
        return results
    except Exception as e:
        return [{"error": str(e)}]

def search_all(query, max_results=5):
    """Search all sources and combine results."""
    print(f"\n  Searching: '{query}'")
    
    print("  [DDG]", end=" ")
    ddg = search_ddg(query, max_results)
    print(f"{len(ddg)} results")
    
    print("  [WIKI]", end=" ")
    wiki = search_wikipedia(query, 3)
    print(f"{len(wiki)} results")
    
    all_results = {
        "query": query,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ddg": ddg,
        "wikipedia": wiki,
    }
    
    # Print summary
    print(f"\n  TOP RESULTS:")
    for r in ddg[:3]:
        print(f"    - {r.get('title', '?')[:70]}")
        print(f"      {r.get('url', '')[:80]}")
        if r.get('snippet'):
            print(f"      {r['snippet'][:100]}")
    
    if wiki:
        print(f"\n  WIKIPEDIA:")
        for r in wiki[:2]:
            print(f"    - {r.get('title', '?')}")
    
    return all_results

# === CLI ===
if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        results = search_all(query)
        
        # Save to file
        search_dir = os.path.expanduser("~/othaiim-12b/searches")
        os.makedirs(search_dir, exist_ok=True)
        filename = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(search_dir, filename)
        with open(filepath, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n  Saved: {filepath}")
    else:
        print("Usage: web_search.py <query>")
        print("Example: web_search.py Bobcat T770 specifications")
