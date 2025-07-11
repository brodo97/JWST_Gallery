import requests
from bs4 import BeautifulSoup as Soup
import Model
from Config import *
import traceback
import logging
import sys
import time

LOGGER : logging.Logger = None
URL = "https://webbtelescope.org"
RESOURCES_URL = f"{URL}/resource-gallery/"
AWS_REQUEST_ID = None
known_resources = []


# Init MongoDB
CONN : Model.MongoDB = None

def send_error_to_admin(error: str, traceback_data: str = ""):
    """
    Send error notification to {TELEGRAM_ADMIN_ID}

    :param error: Error data
    :param traceback_data: Full traceback data (optional)
    :return: None
    """

    LOGGER.info(f"Sending error notification to admin: {TELEGRAM_ADMIN_ID}")
    LOGGER.debug(f"Error details: {error}")
    
    try:
        # Construct error's text
        text = f"*{TELEGRAM_CHANNEL_NAME}*\n"

        if AWS_REQUEST_ID is not None:
            text += f"AWS Request ID: `{AWS_REQUEST_ID}`\n"

        text += "An error occurred:\n"
        text += f"`{error}`\n"
        if traceback_data:
            text += f"Traceback:\n```\n{traceback_data}\n```"

        # Send notification
        response = requests.post(
            url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_ADMIN_ID, "text": text, "parse_mode": "markdown"}
        )
        
        if response.status_code == 200:
            LOGGER.info("Error notification sent successfully to admin")
        else:
            LOGGER.warning(f"Failed to send error notification to admin. Status code: {response.status_code}")
            
    except Exception as e:
        LOGGER.error(f"Failed to send error notification to admin: {str(e)}")

    return


def init_logger() -> None:
    """
    Inizializza il logger dell'applicazione con configurazioni diverse per ambiente locale e AWS Lambda
    
    - Ambiente locale: include timestamp e console handler
    - AWS Lambda: formato semplificato con propagazione al sistema Lambda
    """
    global LOGGER, AWS_REQUEST_ID

    # 1. Configurazione base del logger
    LOGGER = logging.getLogger(APP_NAME)
    LOGGER.setLevel(LOG_LEVEL)
    
    # 2. Configurazione handler di eccezioni globali
    setup_exception_handler()
    
    # 3. Configurazione specifica per ambiente
    if AWS_REQUEST_ID is None:
        configure_local_logging()
    else:
        configure_lambda_logging()
    
    # 4. Assegna logger al modulo Model
    Model.LOGGER = LOGGER
    
    return


def setup_exception_handler() -> None:
    """Configura il gestore delle eccezioni non catturate"""
    def handle_exception(exc_type, exc_value, exc_traceback):
        # Ignora KeyboardInterrupt per permettere chiusura pulita
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Log eccezione e invia notifica admin
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        LOGGER.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        send_error_to_admin(error=f"Uncaught exception: {exc_value}", traceback_data=tb_str)
        sys.exit(1)

    sys.excepthook = handle_exception


def configure_local_logging() -> None:
    """Configura il logging per esecuzione locale"""
    # Formato con timestamp per esecuzione locale
    log_format = "%(asctime)s - {%(filename)s:%(lineno)d} - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format, "%Y-%m-%d %H:%M:%S")
    
    # Aggiungi console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(formatter)
    LOGGER.addHandler(console_handler)
    
    LOGGER.info(f"{APP_NAME} started with log level: {LOG_LEVEL} (Local execution)")


def configure_lambda_logging() -> None:
    """Configura il logging per AWS Lambda"""
    # Rimuovi tutti gli handler esistenti per evitare duplicazione
    for handler in LOGGER.handlers[:]:
        LOGGER.removeHandler(handler)
    
    # AWS Lambda gestisce automaticamente timestamp e request ID
    LOGGER.propagate = True
    
    LOGGER.info(f"{APP_NAME} started with log level: {LOG_LEVEL} (AWS Lambda execution)")


def get_known_resources():
    """
    Populate {known_resources}
    :return: None
    """

    global known_resources

    LOGGER.info("Loading known resources from database")
    
    try:
        # Query known IDs
        count = 0
        for document in CONN.get_all_resources():
            _, identifier = document
            known_resources.append(identifier)
            count += 1

    except Exception as e:
        LOGGER.error(f"Error loading known resources: {str(e)}")
        raise

    return


def sanitize_telegram_text(text: str) -> str:
    """
    Sanitize text for Telegram Markdown to prevent parsing errors
    
    :param text: Text to sanitize
    :return: Sanitized text safe for Telegram Markdown
    """
    if not text:
        return ""
    
    # Characters that need to be escaped in Telegram MarkdownV2
    markdown_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    # Escape special markdown characters
    for char in markdown_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def create_telegram_caption(title: str, description: str, link: str) -> str:
    """
    Create a properly formatted Telegram caption with escaped Markdown
    
    :param title: News title
    :param description: News description  
    :param link: News link
    :return: Formatted and safe caption for Telegram
    """
    # Sanitize all text components
    safe_title = sanitize_telegram_text(title.strip())
    safe_description = sanitize_telegram_text(description.strip())
    safe_link = sanitize_telegram_text(link)
    
    # Create caption with escaped text
    caption = f"*{safe_title}*\n\n"
    caption += f"{safe_description}\n\n"
    caption += f"Link to the full article: [Link]({URL}{safe_link})"
    
    return caption


def send_news():
    """
    Send new (unsent) JWST news!

    :return: None
    """

    LOGGER.info("Starting to send unsent news to Telegram")
    
    try:
        # Query unsent messages
        news_count = 0
        for document in CONN.get_unsent_resources():
            time.sleep(0.1)  # Sleep to avoid hitting Telegram API limits too quickly
            _id, news_id, title, description, image_url, link = document
            news_count += 1
            
            LOGGER.info(f"Processing news {news_count}: {news_id} - {title[:50]}...")

            # Create safe Telegram caption
            caption = create_telegram_caption(title, description, link)

            # If the caption surpass the 1024 char limit, cut the description
            original_length = len(caption)
            if len(caption) > 1024:
                # Calculate how much to remove from description
                excess_chars = len(caption) - 1024 + 3  # +3 for "..."
                
                # Trim description and recreate caption
                trimmed_description = description[:-excess_chars] + "..."
                caption = create_telegram_caption(title, trimmed_description, link)
                
                LOGGER.debug(f"Caption too long ({original_length} chars), truncated description for news {news_id}")

            LOGGER.debug(f"Sending Telegram message for news {news_id} to channel {TELEGRAM_CHANNEL_ID}")
            LOGGER.debug(f"Caption length: {len(caption)} chars")
            
            # Send notification
            response = requests.post(
                url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                data={
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "caption": caption,
                    "parse_mode": "MarkdownV2",
                    "photo": image_url}
            )

            # Convert response into a json object
            response = response.json()

            # If response "ok" status is False, try with HTML parsing or plain text
            if response["ok"] is False:
                LOGGER.warning(f"MarkdownV2 failed for news {news_id}: {response.get('description', 'Unknown error')}")
                
                # Try with HTML parsing as fallback
                html_caption = f"<b>{title.strip()}</b>\n\n{description.strip()}\n\n<a href='{URL}{link}'>Link to the full article</a>"
                
                # Check HTML caption length and truncate if needed
                if len(html_caption) > 1024:
                    excess_chars = len(html_caption) - 1024 + 3
                    trimmed_desc = description.strip()[:-excess_chars] + "..."
                    html_caption = f"<b>{title.strip()}</b>\n\n{trimmed_desc}\n\n<a href='{URL}{link}'>Link to the full article</a>"
                    LOGGER.debug(f"HTML caption also truncated for news {news_id}")
                
                LOGGER.info(f"Retrying with HTML format for news {news_id}")
                response = requests.post(
                    url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                    data={
                        "chat_id": TELEGRAM_CHANNEL_ID,
                        "caption": html_caption,
                        "parse_mode": "HTML",
                        "photo": image_url}
                )
                
                response = response.json()
                
                # If HTML also fails, try without any formatting
                if response["ok"] is False:
                    LOGGER.warning(f"HTML also failed for news {news_id}: {response.get('description', 'Unknown error')}")
                    
                    plain_caption = f"{title.strip()}\n\n{description.strip()}\n\nLink: {URL}{link}"
                    
                    # Check plain caption length and truncate if needed
                    if len(plain_caption) > 1024:
                        excess_chars = len(plain_caption) - 1024 + 3
                        trimmed_desc = description.strip()[:-excess_chars] + "..."
                        plain_caption = f"{title.strip()}\n\n{trimmed_desc}\n\nLink: {URL}{link}"
                        LOGGER.debug(f"Plain text caption also truncated for news {news_id}")
                    
                    LOGGER.info(f"Retrying with plain text for news {news_id}")
                    response = requests.post(
                        url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                        data={
                            "chat_id": TELEGRAM_CHANNEL_ID,
                            "caption": plain_caption,
                            "photo": image_url}
                    )
                    
                    response = response.json()

            # Final check - if still failing, raise exception
            if response["ok"] is False:
                error_msg = f"Error while sending news {news_id!r} - {_id!r}: {response['description']}"
                LOGGER.error(error_msg)
                raise Exception(error_msg)

            message_id = response["result"]["message_id"]
            LOGGER.info(f"Successfully sent news {news_id} with Telegram message ID: {message_id}")

            # Else, update the document on MongoDB
            CONN.update_to_sent(
                _id=_id,
                message_id=message_id
            )

        if news_count == 0:
            LOGGER.info("No unsent news found")
        else:
            LOGGER.info(f"Successfully processed and sent {news_count} news items")
            
    except Exception as e:
        LOGGER.error(f"Error in send_news function: {str(e)}")
        raise

    return


def parse_resources(data: str):
    """
    Parse JWST news data into something readable (for the script)

    :param data: JWST news data
    :return: Execution status, Execution info
    :rtype: tuple[bool, str]
    """

    global known_resources

    LOGGER.info("Parsing JWST resources data")
    
    try:
        # Convert text result into BeautifulSoup4 object
        page = Soup(data, "html.parser")

        # Cycle all divs, with class = "ad-research-box"
        divs = page.find_all("div", {"class": "ad-research-box"})
        LOGGER.debug(f"Found {len(divs)} resource divs to process")
        
        new_resources_count = 0
        
        # reversed is used to sort div from less to more recent
        for div in reversed(divs):
            try:
                # Get news' title
                title_element = div.find("p")
                if not title_element:
                    LOGGER.warning("Skipping div: no title element found")
                    continue
                title = title_element.text.strip()

                # Get news' description
                img_element = div.find("img")
                if not img_element:
                    LOGGER.warning(f"Skipping div with title '{title}': no img element found")
                    continue
                    
                description = img_element.get("alt")
                if not description:
                    LOGGER.warning(f"No alt text found for image in '{title}', using title as description")
                    description = title

                # Get image srcset
                img_srcset = img_element.get("srcset")
                if not img_srcset:
                    LOGGER.warning(f"No srcset found for image in '{title}', trying src attribute")
                    img = img_element.get("src")
                    if not img:
                        LOGGER.warning(f"Skipping div with title '{title}': no image source found")
                        continue
                else:
                    # Extract 1 src from the set
                    img = img_srcset.split(", ")[0]
                    img = img.split(" ")[0]
                
                img = img.replace("//", "https://")

                # If the image host is missing, presume {URL}, the source of the resources
                if "http" not in img:
                    img = f"{URL}/{img}"

                # Get news' link
                link_element = div.find("a")
                if not link_element:
                    LOGGER.warning(f"Skipping div with title '{title}': no link element found")
                    continue
                    
                link = link_element.get("href")
                if not link:
                    LOGGER.warning(f"Skipping div with title '{title}': no href attribute found")
                    continue
                    
                link = link.split("?")[0]

                # Generate a news id
                news_id = link.split("/")[-1]
                if not news_id:
                    LOGGER.warning(f"Skipping div with title '{title}': could not generate news ID from link")
                    continue

                # If the news is known, continue
                if news_id in known_resources:
                    LOGGER.debug(f"Resource {news_id} already known, skipping")
                    continue

                LOGGER.info(f"Found new resource: {news_id} - {title[:50]}...")
                
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
                
                new_resources_count += 1
                
            except Exception as e:
                LOGGER.error(f"Error processing individual resource div: {str(e)}")
                continue  # Skip this div and continue with the next one

        LOGGER.info(f"Successfully parsed resources data, found {new_resources_count} new resources")
        return True, ""
        
    except Exception as e:
        error_msg = f"Error parsing resources data: {str(e)}"
        LOGGER.error(error_msg)
        return False, error_msg


def parse_articles(data: str):
    """
    Parse JWST articles data into something readable (for the script)

    :param data: JWST article data
    :return: Execution status, Execution info
    :rtype: tuple[bool, str]
    """

    global known_resources

    LOGGER.info("Parsing JWST articles data")
    
    try:
        # Convert text result into BeautifulSoup4 object
        page = Soup(data, "html.parser")

        # Cycle all divs, with class = "news-listing"
        divs = page.find_all("div", {"class": "news-listing"})
        LOGGER.debug(f"Found {len(divs)} article divs to process")
        
        new_articles_count = 0
        
        # reversed is used to sort div from less to more recent
        for div in reversed(divs):
            try:
                # Get article's title
                title_element = div.find("h4")
                if not title_element:
                    LOGGER.warning("Skipping article div: no h4 title element found")
                    continue
                title = title_element.text.strip()

                # Get article's description
                description_element = div.find("p", {"class": "article-description"})
                if not description_element:
                    LOGGER.warning(f"No description found for article '{title}', using title as description")
                    description = title
                else:
                    description = description_element.text.strip()

                # Get article's image srcset
                img_element = div.find("img")
                if not img_element:
                    LOGGER.warning(f"Skipping article with title '{title}': no img element found")
                    continue
                    
                img_srcset = img_element.get("srcset")
                if not img_srcset:
                    LOGGER.warning(f"No srcset found for image in article '{title}', trying src attribute")
                    img = img_element.get("src")
                    if not img:
                        LOGGER.warning(f"Skipping article with title '{title}': no image source found")
                        continue
                else:
                    # Extract 1 src from the set
                    img = img_srcset.split(", ")[0]
                    img = img.split(" ")[0]

                img = img.replace("//", "https://")

                # If the image host is missing, presume {URL}, the source of the articles
                if "http" not in img:
                    img = f"{URL}/{img}"

                # Get article's link
                link_element = div.find("a")
                if not link_element:
                    LOGGER.warning(f"Skipping article with title '{title}': no link element found")
                    continue
                    
                link = link_element.get("href")
                if not link:
                    LOGGER.warning(f"Skipping article with title '{title}': no href attribute found")
                    continue
                    
                link = link.split("?")[0]

                # Generate an article ID
                article_id = link.split("/")[-1]
                if not article_id:
                    LOGGER.warning(f"Skipping article with title '{title}': could not generate article ID from link")
                    continue

                # If the article is known, continue
                if article_id in known_resources:
                    LOGGER.debug(f"Article {article_id} already known, skipping")
                    continue

                LOGGER.info(f"Found new article: {article_id} - {title[:50]}...")

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
                
                new_articles_count += 1
                
            except Exception as e:
                LOGGER.error(f"Error processing individual article div: {str(e)}")
                continue  # Skip this div and continue with the next one

        LOGGER.info(f"Successfully parsed articles data, found {new_articles_count} new articles")
        return True, ""
        
    except Exception as e:
        error_msg = f"Error parsing articles data: {str(e)}"
        LOGGER.error(error_msg)
        return False, error_msg


def get_resources():
    """
    Get JWST's latest news from {RESOURCES_URL}/*

    :return: Execution status, Execution info
    :rtype: tuple[bool, str]
    """

    LOGGER.info(f"Starting to fetch JWST resources from {RESOURCES_URL}")
    
    try:
        # Open a session to make the requests all together
        with requests.Session() as session:
            # Update session's user-agent header to make it look more "human"
            session.headers.update({
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
            })
            
            LOGGER.debug("Created HTTP session with user-agent header")
            
            # For every different resource type
            paths = ["images", "videos", "articles", "other-resources"]
            LOGGER.info(f"Processing {len(paths)} resource paths: {paths}")
            
            for path in paths:
                url = RESOURCES_URL + path
                LOGGER.info(f"Fetching data from: {url}")
                
                # Make a get request to the URL
                response = session.get(url=url)

                # If the response status code differ from 200, then something occurred. Return an error
                if response.status_code != 200:
                    error_msg = f"get_resources() returned status code = {response.status_code} on path: {path!r}"
                    LOGGER.error(error_msg)
                    return False, error_msg

                LOGGER.debug(f"Successfully fetched {len(response.text)} characters from {path}")

                # Parse JWST data
                # If path = "articles", parse the data using a different function, the webpage structure differ, so a
                # different method of data extraction must be used
                if path == "articles":
                    LOGGER.debug(f"Using article parser for path: {path}")
                    result, data = parse_articles(data=response.text)
                else:
                    LOGGER.debug(f"Using resource parser for path: {path}")
                    result, data = parse_resources(data=response.text)

                # An error occurred while parsing data?
                if result is False:
                    error_msg = data + f" on {response.url}"
                    LOGGER.error(f"Parsing failed for {path}: {error_msg}")
                    raise Exception(error_msg)
                    
                LOGGER.info(f"Successfully processed path: {path}")

        # Return ok
        LOGGER.info("Successfully fetched and processed all JWST resources")
        return True, ""
        
    except Exception as e:
        error_msg = f"Error in get_resources(): {str(e)}"
        LOGGER.error(error_msg)
        return False, error_msg


def main():
    """
    Main process
    :return: None
    """

    global CONN

    LOGGER.info("=== JWST Gallery Bot Main Process Started ===")
    
    try:
        CONN = Model.MongoDB(
            uri=MONGODB_URI,
            certificate=MONGODB_CERTIFICATE,
            database=MONGODB_DATABASE,
            collection=MONGODB_COLLECTION
        )

        # Init {known_resources} array
        get_known_resources()

        LOGGER.info("Fetching latest JWST resources...")
        # Get JWST news
        result, data = get_resources()

        # An error occurred while getting data?
        if result is False:
            error_msg = f"Failed to get resources: {data}"
            LOGGER.error(error_msg)
            raise Exception(error_msg)

        LOGGER.info("Processing and sending new news...")
        # Send new news
        send_news()

        LOGGER.info("=== JWST Gallery Bot Main Process Completed Successfully ===")
        
    except Exception as e:
        LOGGER.error(f"Critical error in main process: {str(e)}")
        raise
    finally:
        # Ensure database connection is closed
        if CONN is not None:
            try:
                CONN.close()
                LOGGER.info("MongoDB connection closed")
            except Exception as e:
                LOGGER.warning(f"Error closing MongoDB connection: {str(e)}")

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

    # Initialize logger first
    init_logger()
    LOGGER.info(f"=== AWS Lambda Function Started ===")
    LOGGER.info(f"AWS Request ID: {AWS_REQUEST_ID}")
    LOGGER.info(f"Function Name: {lambda_context.function_name}")
    LOGGER.info(f"Function Version: {lambda_context.function_version}")
    LOGGER.info(f"Memory Limit: {lambda_context.memory_limit_in_mb}MB")
    LOGGER.info(f"Remaining Time: {lambda_context.get_remaining_time_in_millis()}ms")

    try:
        main()
        LOGGER.info("=== AWS Lambda Function Completed Successfully ===")
    except Exception as e:
        LOGGER.error(f"=== AWS Lambda Function Failed with Error: {str(e)} ===")
        raise

    return


if __name__ == "__main__":
    # Initialize logger for local execution
    init_logger()
    LOGGER.info("=== Local Execution Started ===")
    
    try:
        main()
        LOGGER.info("=== Local Execution Completed Successfully ===")
    except Exception as e:
        LOGGER.error(f"=== Local Execution Failed with Error: {str(e)} ===")
        raise
