import os
import sys
import json
import requests
from dotenv import load_dotenv

# Ensure UTF-8 output encoding for Windows terminals
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load environment variables from .env file
load_dotenv()

TMDB_API_KEY = os.getenv("api_key") or os.getenv("TMDB_API_KEY")

# Primary & Fallback API hosts (api.tmdb.org avoids ISP/DNS blocks present on api.themoviedb.org)
API_HOSTS = [
    "https://api.tmdb.org/3",
    "https://api.themoviedb.org/3"
]
IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

class TMDBClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or TMDB_API_KEY
        if not self.api_key:
            raise ValueError("TMDB API Key is missing! Please make sure 'api_key' is set in your .env file.")
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TMDB-Client/1.0",
            "Accept": "application/json"
        })
        self.base_url = API_HOSTS[0]

    def _request(self, endpoint: str, params: dict = None) -> dict:
        """Helper to send requests with automatic domain fallback."""
        if params is None:
            params = {}
        params["api_key"] = self.api_key

        last_error = None
        for host in API_HOSTS:
            url = f"{host}/{endpoint.lstrip('/')}"
            try:
                response = self.session.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    self.base_url = host  # Remember working host
                    return response.json()
                elif response.status_code == 401:
                    raise ValueError(f"Unauthorized (401): Invalid TMDB API key '{self.api_key}'.")
                response.raise_for_status()
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                break

        if last_error:
            raise last_error
        raise RuntimeError(f"Failed to fetch {endpoint} from all TMDB API endpoints.")

    def verify_api_key(self) -> bool:
        """Checks if the provided TMDB API key is valid."""
        try:
            data = self._request("authentication")
            return data.get("success", False)
        except Exception as e:
            print(f"[Error] Failed to connect to TMDB: {e}")
            return False

    def get_poster_url(self, poster_path: str, size: str = "w500") -> str:
        """
        Returns full URL for the movie poster image.
        Sizes: 'w92', 'w154', 'w185', 'w342', 'w500', 'w780', 'original'
        """
        if not poster_path:
            return ""
        return f"{IMAGE_BASE_URL}/{size}{poster_path}"

    def get_backdrop_url(self, backdrop_path: str, size: str = "original") -> str:
        """
        Returns full URL for the backdrop banner image.
        Sizes: 'w300', 'w780', 'w1280', 'original'
        """
        if not backdrop_path:
            return ""
        return f"{IMAGE_BASE_URL}/{size}{backdrop_path}"

    def get_popular_movies(self, page: int = 1) -> dict:
        """Fetches list of currently popular movies."""
        return self._request("movie/popular", {"page": page, "language": "en-US"})

    def get_trending_movies(self, time_window: str = "day") -> dict:
        """Fetches trending movies ('day' or 'week')."""
        return self._request(f"trending/movie/{time_window}")

    def get_top_rated_movies(self, page: int = 1) -> dict:
        """Fetches list of top rated movies."""
        return self._request("movie/top_rated", {"page": page, "language": "en-US"})

    def get_movie_details(self, movie_id: int) -> dict:
        """Fetches detailed information for a specific movie including cast, crew, videos, and keywords."""
        return self._request(
            f"movie/{movie_id}",
            {"append_to_response": "credits,videos,keywords,release_dates", "language": "en-US"}
        )

    def search_movies(self, query: str, page: int = 1) -> dict:
        """Searches movies by title or keyword."""
        return self._request("search/movie", {"query": query, "page": page, "language": "en-US"})

    def download_image(self, image_url: str, output_path: str) -> bool:
        """Downloads an image from TMDB and saves it locally."""
        if not image_url:
            return False
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        try:
            response = self.session.get(image_url, stream=True, timeout=15)
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(1024 * 8):
                        f.write(chunk)
                return True
        except Exception as e:
            print(f"[Warning] Failed to download {image_url}: {e}")
        return False


def display_movie(movie: dict, client: TMDBClient, idx: int = 1):
    """Prints formatted movie information and poster URLs."""
    title = movie.get("title", "N/A")
    release_date = movie.get("release_date", "N/A")
    rating = movie.get("vote_average", "N/A")
    vote_count = movie.get("vote_count", 0)
    poster_path = movie.get("poster_path")
    backdrop_path = movie.get("backdrop_path")
    overview = movie.get("overview", "No overview provided.")
    
    poster_w500 = client.get_poster_url(poster_path, size="w500")
    poster_original = client.get_poster_url(poster_path, size="original")
    backdrop_url = client.get_backdrop_url(backdrop_path, size="original")

    year = release_date.split("-")[0] if release_date and release_date != "N/A" else "N/A"

    print("=" * 85)
    print(f"[{idx}] 🎬 {title} ({year})")
    print("=" * 85)
    print(f"⭐ Rating:            {rating}/10 ({vote_count:,} votes)")
    print(f"📅 Release Date:      {release_date}")
    print(f"🖼️ Poster URL (w500):     {poster_w500 or 'Not Available'}")
    print(f"🖼️ Poster URL (Full HD):  {poster_original or 'Not Available'}")
    print(f"🌄 Backdrop Banner:       {backdrop_url or 'Not Available'}")
    print("-" * 85)
    print(f"📝 Overview:\n{overview}")
    print("=" * 85 + "\n")


def run_demo():
    print("=" * 85)
    print("            TMDB API VERIFICATION & MOVIE CONTENT EXTRACTOR            ")
    print("=" * 85 + "\n")

    client = TMDBClient()

    print("Step 1: Checking TMDB API Key from .env...")
    is_valid = client.verify_api_key()

    if not is_valid:
        print("\n❌ API Key verification failed. Please verify your TMDB key in .env.")
        return

    print("✅ SUCCESS: Your TMDB API Key is VALID and ACTIVE!\n")

    # Step 2: Fetch Popular Movies
    print("Step 2: Fetching currently popular movies from TMDB...\n")
    popular_response = client.get_popular_movies(page=1)
    movies = popular_response.get("results", [])

    print(f"Found {len(movies)} popular movies on page 1.\n")

    # Display Top 5 Movies with posters and content
    download_folder = os.path.join(os.path.dirname(__file__), "posters")

    for i, movie in enumerate(movies[:5], start=1):
        display_movie(movie, client, idx=i)
        
        # Download poster locally as demonstration
        poster_path = movie.get("poster_path")
        if poster_path:
            clean_title = "".join(c for c in movie.get("title", f"movie_{i}") if c.isalnum() or c in (" ", "_", "-")).rstrip()
            local_filename = os.path.join(download_folder, f"{clean_title}_poster.jpg")
            poster_w500 = client.get_poster_url(poster_path, size="w500")
            print(f"⬇️ Downloading poster for '{movie.get('title')}'...")
            downloaded = client.download_image(poster_w500, local_filename)
            if downloaded:
                print(f"   Saved to: {local_filename}\n")

    # Step 3: Fetch Deep Details for the #1 Popular Movie
    if movies:
        top_movie = movies[0]
        top_movie_id = top_movie["id"]
        print(f"Step 3: Fetching Full Deep Metadata for #1 Movie: '{top_movie['title']}' (ID: {top_movie_id})...\n")
        
        details = client.get_movie_details(top_movie_id)
        genres = [g["name"] for g in details.get("genres", [])]
        runtime = details.get("runtime", "N/A")
        budget = f"${details.get('budget', 0):,}" if details.get('budget') else "N/A"
        revenue = f"${details.get('revenue', 0):,}" if details.get('revenue') else "N/A"
        tagline = details.get("tagline", "")
        status = details.get("status", "N/A")
        cast = [c["name"] for c in details.get("credits", {}).get("cast", [])[:6]]
        directors = [c["name"] for c in details.get("credits", {}).get("crew", []) if c.get("job") == "Director"]
        
        print("+" + "-" * 83 + "+")
        print(f"| 🎬 Deep Details: {top_movie['title']}")
        print("+" + "-" * 83 + "+")
        print(f"| 🏷️ Tagline:       {tagline or 'N/A'}")
        print(f"| 🎭 Genres:        {', '.join(genres) if genres else 'N/A'}")
        print(f"| ⏱️ Runtime:       {runtime} minutes")
        print(f"| 📌 Status:        {status}")
        print(f"| 💰 Budget:        {budget}")
        print(f"| 💵 Revenue:       {revenue}")
        print(f"| 🎬 Director(s):   {', '.join(directors) if directors else 'N/A'}")
        print(f"| 🌟 Star Cast:     {', '.join(cast) if cast else 'N/A'}")
        print("+" + "-" * 83 + "+\n")

        # Save extracted popular movies into a JSON file for quick access
        output_json_path = os.path.join(os.path.dirname(__file__), "popular_movies.json")
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(movies[:10], f, indent=2, ensure_ascii=False)
        print(f"💾 Saved top 10 movies full JSON data to: {output_json_path}\n")

    print("🎉 All operations completed successfully!")


if __name__ == "__main__":
    run_demo()
