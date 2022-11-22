import requests
from bs4 import BeautifulSoup as Soup
from Config import *
import sqlite3

known_news = []

CONN = sqlite3.connect("Database.db", check_same_thread=False)


def get_known_news():
    """
    Populate {known_news}
    :return: None
    """

    global known_news

    # Query known IDs
    for row in CONN.execute("SELECT ID FROM News;"):
        known_news.append(row[0])

    return


def send_error_to_admin(error: str):
    """
    Send error notification to {TELEGRAM_ADMIN_ID}

    :param error: Error data
    :return: None
    """

    # Construct error's text
    text = f"*{TELEGRAM_CHANNEL_NAME}*\n"
    text += "An error occurred:\n"
    text += f"`{error}`"

    # Send notification
    requests.post(
        url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_ADMIN_ID, "text": text, "parse_mode": "markdown"}
    )

    return


def send_news():
    """
    Send new (unsent) JWST news!

    :return: None
    """

    # Query unsent messages
    for row in CONN.execute(
        "SELECT ID, Title, Description, ImageURL, Link FROM News WHERE Sent = 0;"
    ):
        news_id, title, description, image_url, link = row

        # Construct the news caption
        text = f"*{title}*\n\n"
        text += f"{description}\n\n"
        text += f"Link to the full article: [Link]({URL}{link})"

        # If the caption surpass the 1024 char limit, cut the description
        if len(text) > 1024:
            remove_from_description = len(text) - 1024 + 3
            description = description[:-remove_from_description] + "..."

            # Reconstruct the news caption
            text = f"*{title}*\n\n"
            text += f"{description}\n\n"
            text += f"Link to the full article: [Link]({URL}{link})"

        # Send notification
        response = requests.post(
            url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
            data={"chat_id": TELEGRAM_CHANNEL_ID, "caption": text, "parse_mode": "markdown", "photo": image_url}
        )

        # Convert response into a json object
        response = response.json()

        # If response "ok" status is False, send error to admin
        if response["ok"] is False:
            send_error_to_admin(f"News({news_id})" + response["description"])
            break

        # Else, update the sell value of the news to the corresponding message ID (on Telegram)
        CONN.execute(
            "UPDATE News SET Sent = ? WHERE ID = ?;",
            [response["result"]["message_id"], news_id]
        )

        # Commit changes
        CONN.commit()

    return


def get_data():
    """
    Get JWST's news from {URL}

    :return: Execution status, data
    :rtype: tuple[bool, str]
    """

    # Make a get request to the URL
    response = requests.get(url=NEWS_URL)

    # If the response status code differ from 200, then something occurred. Return an error
    if response.status_code != 200:
        return False, f"get_data() returned status code = {response.status_code}"

    # Return data
    return True, response.text


def parse_data(data: str):
    """
    Parse JWST news data into something readable (for the script)

    :param data: JWST news data
    :return: Execution status, Execution info
    :rtype: tuple[bool, str]
    """

    global known_news

    # Convert text result into BeautifulSoup4 object
    page = Soup(data, "html.parser")

    try:
        # Cycle all divs, with class = "ad-research-box"
        # reversed is used to sort div from less to more recent
        for div in reversed(page.find_all("div", {"class": "ad-research-box"})):
            # Get news' title
            title = div.find("p").text

            # Get news' description
            description = div.find("img").get("alt")

            # Get image srcset
            img = div.find("img").get("srcset")

            # Extract 1 src from the set
            img = img.split(", ")[0]
            img = img.split(" ")[0]
            img = img.replace("//", "https://")

            # Get news' link
            link = div.find("a").get("href")
            link = link.split("?")[0]

            # Generate a news id
            news_id = link.split("/")[-1]

            if news_id in known_news:
                known_news.append(news_id)
                continue

            # Update news DB
            CONN.execute(
                "INSERT INTO News (ID, Title, Description, ImageURL, Link) VALUES (?, ?, ?, ?, ?);",
                [news_id, title, description, img, link]
            )

        # Commit changes
        CONN.commit()

    except Exception as e:  # If an exception occur, rollback and return the error
        CONN.rollback()
        return False, f"parse_data() something went wrong: {e}"

    return True, ""


def main():
    """
    Main process
    :return: None
    """

    # Init {known_news} array
    get_known_news()

    # Get JWST data
    result, data = get_data()

    # An error occurred while getting data?
    if result is False:
        send_error_to_admin(data)

        # Close DB
        CONN.close()

        exit()

    # Parse JWST data
    result, data = parse_data(data)

    # An error occurred while parsing data?
    if result is False:
        send_error_to_admin(data)

        # Close DB
        CONN.close()

        exit()

    # Send new news
    send_news()

    # Close DB when everything is done
    CONN.close()

    return


if __name__ == "__main__":
    main()


