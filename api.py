import os
import sys
import json
import argparse
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

    def search_movies(self, query: str, page: int = 1) -> dict:
        """Searches movies by title or keyword."""
        return self._request("search/movie", {"query": query, "page": page, "language": "en-US"})

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
        """Fetches complete metadata for a specific movie including cast, crew, videos, and keywords."""
        return self._request(
            f"movie/{movie_id}",
            {"append_to_response": "credits,videos,keywords,release_dates", "language": "en-US"}
        )

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

    def search_and_get_movie(self, movie_name: str, download_poster: bool = True, save_json: bool = True) -> dict:
        """
        Search for a movie by name, fetch all its metadata and posters.
        """
        search_results = self.search_movies(movie_name)
        results = search_results.get("results", [])

        if not results:
            print(f"\n❌ No movies found matching '{movie_name}'.")
            return None

        # Take the best matching result
        best_match = results[0]
        movie_id = best_match["id"]

        print(f"\n🎯 Found match: '{best_match.get('title')}' (ID: {movie_id})")
        print("⏳ Fetching complete metadata from TMDB...\n")

        # Fetch deep details (cast, crew, runtime, budget, revenue, videos, etc.)
        details = self.get_movie_details(movie_id)

        # Poster & Backdrop URLs
        poster_path = details.get("poster_path")
        backdrop_path = details.get("backdrop_path")
        poster_w500 = self.get_poster_url(poster_path, size="w500")
        poster_hd = self.get_poster_url(poster_path, size="original")
        backdrop_hd = self.get_backdrop_url(backdrop_path, size="original")

        # Metadata extraction
        title = details.get("title", "N/A")
        original_title = details.get("original_title", "N/A")
        release_date = details.get("release_date", "N/A")
        year = release_date.split("-")[0] if release_date and release_date != "N/A" else "N/A"
        rating = details.get("vote_average", "N/A")
        vote_count = details.get("vote_count", 0)
        genres = [g["name"] for g in details.get("genres", [])]
        runtime = details.get("runtime", "N/A")
        budget = f"${details.get('budget', 0):,}" if details.get('budget') else "N/A"
        revenue = f"${details.get('revenue', 0):,}" if details.get('revenue') else "N/A"
        tagline = details.get("tagline", "")
        overview = details.get("overview", "No overview provided.")
        status = details.get("status", "N/A")
        homepage = details.get("homepage", "")
        spoken_languages = [l["english_name"] for l in details.get("spoken_languages", [])]

        # Cast & Crew
        credits = details.get("credits", {})
        top_cast = [c["name"] + (f" as '{c['character']}'" if c.get("character") else "") for c in credits.get("cast", [])[:6]]
        directors = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
        producers = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Producer"][:3]

        # Trailer links
        videos = details.get("videos", {}).get("results", [])
        trailers = [f"https://www.youtube.com/watch?v={v['key']}" for v in videos if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser")]

        # Display rich metadata box
        print("=" * 85)
        print(f"🎬 {title} ({year})")
        print("=" * 85)
        if tagline:
            print(f"🏷️ Tagline:          \"{tagline}\"")
        if original_title != title:
            print(f"🔤 Original Title:   {original_title}")
        print(f"⭐ TMDB Rating:      {rating}/10 ({vote_count:,} votes)")
        print(f"📅 Release Date:      {release_date} ({status})")
        print(f"🎭 Genres:            {', '.join(genres) if genres else 'N/A'}")
        print(f"⏱️ Runtime:           {runtime} minutes" if runtime != "N/A" else "⏱️ Runtime:           N/A")
        print(f"💰 Budget:            {budget}")
        print(f"💵 Revenue:           {revenue}")
        print(f"🗣️ Languages:         {', '.join(spoken_languages) if spoken_languages else 'N/A'}")
        if homepage:
            print(f"🌐 Official Website:  {homepage}")
        print(f"🎬 Director(s):       {', '.join(directors) if directors else 'N/A'}")
        if producers:
            print(f"💼 Producer(s):       {', '.join(producers)}")
        if top_cast:
            print(f"🌟 Top Cast:          {', '.join(top_cast)}")
        if trailers:
            print(f"🎥 Official Trailer:  {trailers[0]}")
        print("-" * 85)
        print(f"🖼️ Poster (w500):     {poster_w500 or 'Not Available'}")
        print(f"🖼️ Poster (Full HD):  {poster_hd or 'Not Available'}")
        print(f"🌄 Backdrop Banner:   {backdrop_hd or 'Not Available'}")
        print("-" * 85)
        print(f"📝 Overview:\n{overview}")
        print("=" * 85 + "\n")

        # Download poster
        downloaded_file = None
        if download_poster and poster_w500:
            clean_name = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).rstrip()
            posters_dir = os.path.join(os.path.dirname(__file__), "posters")
            downloaded_file = os.path.join(posters_dir, f"{clean_name}_poster.jpg")
            print(f"⬇️ Downloading poster to: {downloaded_file} ...")
            if self.download_image(poster_w500, downloaded_file):
                print(f"✅ Poster saved successfully!\n")

        # Save metadata to JSON
        if save_json:
            clean_name = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).rstrip()
            json_file = os.path.join(os.path.dirname(__file__), f"{clean_name}_metadata.json")
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(details, f, indent=2, ensure_ascii=False)
            print(f"💾 Full metadata JSON saved to: {json_file}\n")

        return details


def interactive_menu():
    client = TMDBClient()

    print("=" * 85)
    print("                     TMDB MOVIE EXPLORER & POSTER EXTRACTOR                   ")
    print("=" * 85)

    if not client.verify_api_key():
        print("❌ Error: Invalid TMDB API Key in .env file.")
        return

    while True:
        print("\nChoose an option:")
        print("  1. Search a Movie by Name (Get Poster + All Metadata)")
        print("  2. Get Currently Popular Movies")
        print("  3. Get Trending Movies (Today)")
        print("  4. Get Top Rated Movies")
        print("  5. Exit")
        
        choice = input("\nEnter choice [1-5]: ").strip()

        if choice == "1":
            movie_name = input("Enter movie name (e.g. Inception, Interstellar, Avatar): ").strip()
            if movie_name:
                client.search_and_get_movie(movie_name)
            else:
                print("Movie name cannot be empty.")

        elif choice == "2":
            print("\nFetching Popular Movies...")
            data = client.get_popular_movies(page=1)
            movies = data.get("results", [])[:5]
            for idx, m in enumerate(movies, 1):
                poster = client.get_poster_url(m.get("poster_path"))
                print(f"\n[{idx}] {m.get('title')} ({m.get('release_date', 'N/A')}) - Rating: {m.get('vote_average')}/10")
                print(f"    Poster: {poster}")
                print(f"    Overview: {m.get('overview', '')[:120]}...")

        elif choice == "3":
            print("\nFetching Trending Movies Today...")
            data = client.get_trending_movies(time_window="day")
            movies = data.get("results", [])[:5]
            for idx, m in enumerate(movies, 1):
                poster = client.get_poster_url(m.get("poster_path"))
                print(f"\n[{idx}] {m.get('title')} ({m.get('release_date', 'N/A')}) - Rating: {m.get('vote_average')}/10")
                print(f"    Poster: {poster}")
                print(f"    Overview: {m.get('overview', '')[:120]}...")

        elif choice == "4":
            print("\nFetching Top Rated Movies...")
            data = client.get_top_rated_movies(page=1)
            movies = data.get("results", [])[:5]
            for idx, m in enumerate(movies, 1):
                poster = client.get_poster_url(m.get("poster_path"))
                print(f"\n[{idx}] {m.get('title')} ({m.get('release_date', 'N/A')}) - Rating: {m.get('vote_average')}/10")
                print(f"    Poster: {poster}")
                print(f"    Overview: {m.get('overview', '')[:120]}...")

        elif choice == "5" or choice.lower() in ("exit", "quit", "q"):
            print("Goodbye! 👋")
            break
        else:
            print("Invalid selection. Please enter a number from 1 to 5.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TMDB Movie Metadata & Poster Extractor")
    parser.add_argument("movie_name", nargs="*", help="Name of the movie to search directly")
    parser.add_argument("--search", "-s", type=str, help="Search movie by title")
    args = parser.parse_args()

    # If movie name provided as command-line arguments (e.g. `python api.py Inception` or `python api.py -s "Avengers Endgame"`)
    query = args.search or (" ".join(args.movie_name) if args.movie_name else "")

    if query.strip():
        client = TMDBClient()
        client.search_and_get_movie(query.strip())
    else:
        interactive_menu()
