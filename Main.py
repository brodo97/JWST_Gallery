import requests
from bs4 import BeautifulSoup as Soup
from Model import MongoDB
from Config import *

URL = "https://webbtelescope.org"
RESOURCES_URL = f"{URL}/resource-gallery/"
AWS_REQUEST_ID = None
known_resources = []

# Init MongoDB
CONN = MongoDB(
    uri=MONGODB_URI,
    certificate=MONGODB_CERTIFICATE,
    database=MONGODB_DATABASE,
    collection=MONGODB_COLLECTION
)


def get_known_resources():
    """
    Populate {known_resources}
    :return: None
    """

    global known_resources

    # Query known IDs
    for document in CONN.get_all_resources():
        _, identifier = document
        known_resources.append(identifier)

    return


def send_error_to_admin(error: str):
    """
    Send error notification to {TELEGRAM_ADMIN_ID}

    :param error: Error data
    :return: None
    """

    # Construct error's text
    text = f"*{TELEGRAM_CHANNEL_NAME}*\n"
    
    if AWS_REQUEST_ID is not None:
        text += f"AWS Request ID: `{AWS_REQUEST_ID}`\n"
    
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
    for document in CONN.get_unsent_resources():
        _id, news_id, title, description, image_url, link = document

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
            send_error_to_admin(f"Resources({news_id})" + response["description"])
            break

        # Else, update the document on MongoDB
        CONN.update_to_sent(
            _id=_id,
            message_id=response["result"]["message_id"]
        )

    return


def parse_resources(data: str):
    """
    Parse JWST news data into something readable (for the script)

    :param data: JWST news data
    :return: Execution status, Execution info
    :rtype: tuple[bool, str]
    """

    global known_resources

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

            # If the news is known, continue
            if news_id in known_resources:
                continue

            # Else, remember it!
            known_resources.append(news_id)

            # Insert the news in the DB
            CONN.insert_new_resource(
                identifier=news_id,
                title=title,
                description=description,
                imageurl=img,
                link=link
            )

    except Exception as e:  # If an exception occur, return the error
        return False, f"parse_data() something went wrong: {e}"

    return True, ""


def parse_articles(data: str):
    """
    Parse JWST articles data into something readable (for the script)

    :param data: JWST article data
    :return: Execution status, Execution info
    :rtype: tuple[bool, str]
    """

    global known_resources

    # Convert text result into BeautifulSoup4 object
    page = Soup(data, "html.parser")

    try:
        # Cycle all divs, with class = "news-listing"
        # reversed is used to sort div from less to more recent
        for div in reversed(page.find_all("div", {"class": "news-listing"})):
            # Get article's title
            title = div.find("h3").text

            # Get article's description
            description = div.find("div", {"class": "article-description"}).text.strip()

            # Get article's image srcset
            img = div.find("img").get("srcset")

            # Extract 1 src from the set
            img = img.split(", ")[0]
            img = img.split(" ")[0]
            img = img.replace("//", "https://")

            # Get article's link
            link = div.find("a").get("href")
            link = link.split("?")[0]

            # Generate an article ID
            article_id = link.split("/")[-1]

            # If the article is known, continue
            if article_id in known_resources:
                continue

            # Else, remember it!
            known_resources.append(article_id)

            # Insert the news in the DB
            CONN.insert_new_resource(
                identifier=article_id,
                title=title,
                description=description,
                imageurl=img,
                link=link
            )

    except Exception as e:  # If an exception occur, return the error
        return False, f"parse_data() something went wrong: {e}"

    return True, ""


def get_resources():
    """
    Get JWST's latest news from {RESOURCES_URL}/*

    :return: Execution status, Execution info
    :rtype: tuple[bool, str]
    """

    # Open a session to make the requests all together
    with requests.Session() as session:
        # For every different resource type
        for path in ["images", "videos", "articles", "other-resources"]:
            # Make a get request to the URL
            response = session.get(url=RESOURCES_URL + path)

            # If the response status code differ from 200, then something occurred. Return an error
            if response.status_code != 200:
                return False, f"get_data() returned status code = {response.status_code} on path: {path!r}"

            # Parse JWST data
            # If path = "articles", parse the data using a different function, the webpage structure differ, so a
            # different method of data extraction must be used
            if path == "articles":
                result, data = parse_articles(data=response.text)
            else:
                result, data = parse_resources(data=response.text)

            # An error occurred while parsing data?
            if result is False:
                send_error_to_admin(data)

                exit()

    # Return ok
    return True, ""


def main():
    """
    Main process
    :return: None
    """

    # Init {known_resources} array
    get_known_resources()

    # Get JWST news
    result, data = get_resources()

    # An error occurred while getting data?
    if result is False:
        send_error_to_admin(data)

        exit()

    # Send new news
    send_news()

    return


def lambda_handler(event, lambda_context):
    """
    AWS Lambda Handler

    I run this bot as an AWS Lambda Function.

    I use this function to handle the 2 positional arguments (event, lambda_context) that Lambda pass to the script.
    I don't really know how to use them... Actually I think I don't even need them.

    :param event: Lambda Argument
    :param lambda_context: Lambda Argument
    :return: None
    """

    # Set AWS_REQUEST_ID for debugging purposes
    global AWS_REQUEST_ID    
    AWS_REQUEST_ID = lambda_context.aws_request_id
    
    main()

    return


if __name__ == "__main__":
    main()
