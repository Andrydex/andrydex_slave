import requests
from bs4 import BeautifulSoup

URL = "https://store.steampowered.com/search/?maxprice=free"


def fetch_free_games():

    response = requests.get(URL, timeout=10)

    soup = BeautifulSoup(response.text, "html.parser")

    games = []

    results = soup.select("a.search_result_row")

    for item in results[:5]:

        title = item.select_one(".title")

        if title:

            games.append({
                "source": "steam",
                "title": title.text.strip(),
                "url": item["href"]
            })

    return games
