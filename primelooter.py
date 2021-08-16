import argparse
import http.cookiejar as cookiejar
import logging
import sys
import time
import traceback
import typing

from playwright.sync_api import sync_playwright, Cookie, Browser


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("impfbot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

log = logging.getLogger()


class AuthException(Exception):
    pass


def loot(cookies, publishers, headless, dump):
    with sync_playwright() as playwright:
        browser: Browser = playwright.firefox.launch(headless=headless)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        authentication_tries = 0
        authenticated = False
        while not authenticated:
            if authentication_tries < 5:
                authentication_tries += 1
            else:
                raise AuthException()
            page.goto("https://gaming.amazon.com/home")
            page.wait_for_load_state('networkidle')

            if not page.query_selector('div.sign-in'):
                authenticated = True

        # Ingame Loot
        loot_offer_xpath = 'xpath=((//div[@data-a-target="offer-list-undefined"])[1] | //div[data-a-target="offer-list-InGameLoot"])//div[@data-test-selector="Offer"]'

        try:
            page.wait_for_selector(loot_offer_xpath, timeout=1000*30)
        except Exception as ex:
            log.error("Could not load loot offers. (timeout)")

        if dump:
            print(page.query_selector('div.home').inner_html())

        elements = page.query_selector_all(loot_offer_xpath)

        if len(elements) == 0:
            log.error(
                "No loot offers found! Did they make some changes to the website? Please report @github if this happens multiple times.")

        for i in range(len(elements)):
            elem = page.query_selector_all(loot_offer_xpath)[i]
            elem.scroll_into_view_if_needed()
            elem.wait_for_selector('p.tw-c-text-alt-2')
            publisher = elem.query_selector(
                'p.tw-c-text-alt-2').text_content()
            game_name = elem.query_selector('h3').text_content()

            if elem.query_selector('div[data-a-target=offer-claim-success]'):
                log.debug("Already claimed %s by %s", game_name, publisher)
                continue
            if publisher not in publishers:
                continue

            with page.expect_navigation():
                log.debug("Try to claim %s from %s", game_name, publisher)
                elem.query_selector(
                    'button[data-a-target=ExternalOfferClaim]').click()
            page.wait_for_selector(
                'div[data-a-target=loot-card-available]')
            try:
                loot_cards = page.query_selector_all(
                    'div[data-a-target=loot-card-available]')

                for loot_card in loot_cards:
                    loot_name = loot_card.query_selector(
                        'h3[data-a-target=LootCardSubtitle]').text_content()
                    log.debug("Try to claim loot %s from %s by %s",
                              loot_name, game_name, publisher)

                    claim_button = loot_card.query_selector(
                        'button[data-test-selector=AvailableButton]')
                    if not claim_button:
                        log.warning(
                            "Could not claim %s from %s by %s (in-game loot)", loot_name, game_name, publisher)
                        continue

                    claim_button.click()
                    page.wait_for_load_state('networkidle')

                    # validate
                    page.wait_for_selector(
                        "div[data-a-target=gms-base-modal]")

                    if page.query_selector('div.gms-success-modal-container'):
                        log.info("Claimed %s (%s)", loot_name, game_name)
                    elif page.query_selector("div[data-test-selector=ProgressBarSection]"):
                        log.warning(
                            "Could not claim %s from %s by %s (account not connected)", loot_name, game_name, publisher)
                    else:
                        log.warning(
                            "Could not claim %s from %s by %s (unknown error)", loot_name, game_name, publisher)
                    if page.query_selector('button[data-a-target=close-modal-button]'):
                        page.query_selector(
                            'button[data-a-target=close-modal-button]').click()
            except Exception as ex:
                print(ex)
            finally:
                page.goto("https://gaming.amazon.com/home")
                page.wait_for_selector(loot_offer_xpath)

        # Games
        loot_offer_xpath = 'xpath=((//div[@data-a-target="offer-list-undefined"])[2] | //div[@data-a-target="offer-list-Game"])//div[@data-test-selector="Offer"]'

        try:
            page.wait_for_selector(loot_offer_xpath, timeout=1000*30)
        except:
            log.error("Could not load game offers. (timeout)")

        elements = page.query_selector_all(loot_offer_xpath)

        if len(elements) == 0:
            log.error(
                "No game offers found! Did they make some changes to the website? Please report @github if this happens multiple times.")

        for elem in elements:
            elem.scroll_into_view_if_needed()
            page.wait_for_load_state('networkidle')

            publisher = elem.query_selector(
                'p.tw-c-text-alt-2').text_content()
            game_name = elem.query_selector('h3').text_content()

            if elem.query_selector('div[data-a-target=offer-claim-success]'):
                log.debug("Already claimed %s by %s", game_name, publisher)
                continue

            log.debug("Try to claim %s", game_name)
            elem.query_selector("button[data-a-target=FGWPOffer]").click()
            log.info("Claimed %s", game_name)

        context.close()
        browser.close()


def read_cookiefile(path: str) -> typing.List[Cookie]:
    jar = cookiejar.MozillaCookieJar(path)
    jar.load()

    _cookies: typing.List[Cookie] = list()

    for _c in jar:
        cookie = Cookie(
            name=_c.name,
            value=_c.value,
            domain=_c.domain,
            path=_c.path,
            expires=_c.expires,
            secure=_c.secure
        )
        _cookies.append(cookie)
    return _cookies


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Notification bot for the lower saxony vaccination portal')

    parser.add_argument('-p', '--publishers',
                        dest='publishers',
                        help='Path to publishers.txt file',
                        required=False,
                        default='publishers.txt')
    parser.add_argument('-c', '--cookies',
                        dest='cookies',
                        help='Path to cookies.txt file',
                        required=False,
                        default='cookies.txt')
    parser.add_argument('-l', '--loop',
                        dest='loop',
                        help='Shall the script loop itself? (Cooldown 24h)',
                        required=False,
                        action='store_true',
                        default=False)

    parser.add_argument('-d', '--dump',
                        dest='dump',
                        help='Dump html to output',
                        required=False,
                        action='store_true',
                        default=False)

    parser.add_argument('-nh', '--no-headless',
                        dest='headless',
                        help='Shall the script not use headless mode?',
                        required=False,
                        action='store_false',
                        default=True)

    arg = vars(parser.parse_args())

    cookies = read_cookiefile(arg['cookies'])

    with open(arg['publishers']) as f:
        publishers = f.readlines()
    publishers = [x.strip() for x in publishers]
    headless = arg['headless']
    dump = arg['dump']

    if arg['loop']:
        while True:
            try:
                log.info("start looting cycle")
                loot(cookies, publishers, headless, dump)
                log.info("finished looting cycle")
            except AuthException:
                log.error("Authentication failed!")
            except Exception as ex:
                log.error("Error %s", ex)
                traceback.print_tb(ex.__traceback__)
                time.sleep(60)
                continue
            time.sleep(60*60*24)
    else:
        try:
            loot(cookies, publishers, headless, dump)
        except AuthException:
            log.error("Authentication failed!")
