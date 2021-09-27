import argparse
import http.cookiejar as cookiejar
import logging
import sys
import time
import traceback
import typing
import json
import typing

from playwright.sync_api import sync_playwright, Cookie, Browser, Page, BrowserContext, ElementHandle


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


class PrimeLooter():

    def __init__(self, cookies, publishers='all', headless=True):
        self.cookies = cookies
        self.publishers = publishers
        self.headless = headless

    def __enter__(self):
        self.playwright = sync_playwright()
        self.browser: Browser = self.playwright.start().chromium.launch(
            headless=self.headless)
        self.context: BrowserContext = self.browser.new_context()
        self.context.add_cookies(self.cookies)
        self.page: Page = self.context.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.page.close()
        self.context.close()
        self.browser.close()
        self.playwright.__exit__()

    @staticmethod
    def exists(tab: Page, selector: str) -> bool:
        if tab.query_selector(selector):
            return True
        return False

    def auth(self) -> None:
        with self.page.expect_response(lambda response:  'https://gaming.amazon.com/graphql' in response.url and 'currentUser' in response.json()['data']) as response_info:
            log.debug('get auth info')
            self.page.goto('https://gaming.amazon.com/home')
            response = response_info.value.json()['data']['currentUser']
            if not response['isSignedIn']:
                Exception('Authentication: Not signed in')
            elif not response['isAmazonPrime']:
                Exception('Authentication: Not a valid Amazon Prime account')
            elif not response['isTwitchPrime']:
                Exception('Authentication: Not a valid Twitch Prime account')

    def get_offers(self) -> typing.List:
        with self.page.expect_response(lambda response:  'https://gaming.amazon.com/graphql' in response.url and 'primeOffers' in response.json()['data']) as response_info:
            log.debug('get offers')
            self.page.goto('https://gaming.amazon.com/home')
            return response_info.value.json()['data']['primeOffers']

    @staticmethod
    def check_eligibility(offer: dict) -> bool:
        if offer['linkedJourney']:
            for suboffer in offer['linkedJourney']['offers']:
                if suboffer['self']['eligibility']:
                    return suboffer['self']['eligibility']['canClaim']
            return False
        elif offer['self']:
            return offer['self']['eligibility']['canClaim']
        else:
            raise Exception(
                f'Could not check offer eligibility status\n{json.dumps(offer, indent=4)}')

    def claim_external(self, url, publisher):
        tab = self.context.new_page()

        with tab.expect_response(lambda response:  'https://gaming.amazon.com/graphql' in response.url and 'journey' in response.json()['data']) as response_info:
            log.debug('get game title')
            tab.goto(url)
            game_name = response_info.value.json(
            )['data']['journey']['assets']['title']

        log.debug("Try to claim %s from %s", game_name, publisher)
        tab.wait_for_selector(
            'div[data-a-target=loot-card-available]')

        try:
            loot_cards = tab.query_selector_all(
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
                tab.wait_for_load_state('networkidle')

                # validate
                tab.wait_for_selector(
                    "div[data-a-target=gms-base-modal]")

                if PrimeLooter.exists(tab, 'div.gms-success-modal-container'):
                    log.info("Claimed %s (%s)", loot_name, game_name)

                elif PrimeLooter.exists(tab, "div[data-test-selector=ProgressBarSection]"):
                    log.warning(
                        "Could not claim %s from %s by %s (account not connected)", loot_name, game_name, publisher)
                else:
                    log.warning(
                        "Could not claim %s from %s by %s (unknown error)", loot_name, game_name, publisher)
                if tab.query_selector('button[data-a-target=close-modal-button]'):
                    tab.query_selector(
                        'button[data-a-target=close-modal-button]').click()
        except Exception as ex:
            print(ex)
            log.error(
                f"An error occured ({publisher}/{game_name})! Did they make some changes to the website? Please report @github if this happens multiple times.")
        tab.close()

    def claim_direct(self):
        tab = self.context.new_page()
        tab.goto('https://gaming.amazon.com/home')

        FGWP_XPATH = 'xpath=//button[@data-a-target="FGWPOffer"]/ancestor::div[@data-test-selector="Offer"]'

        elements = self.page.query_selector_all(FGWP_XPATH)

        if len(elements) == 0:
            log.error(
                "No direct offers found! Did they make some changes to the website? Please report @github if this happens multiple times.")

        for elem in elements:
            elem.scroll_into_view_if_needed()
            self.page.wait_for_load_state('networkidle')

            publisher = elem.query_selector(
                'p.tw-c-text-alt-2').text_content()
            game_name = elem.query_selector('h3').text_content()

            log.debug("Try to claim %s by %s", game_name, publisher)
            elem.query_selector("button[data-a-target=FGWPOffer]").click()
            log.info("Claimed %s by %s", game_name, publisher)

        tab.close()

    def run(self, dump: bool = False):
        self.auth()

        if dump:
            print(self.page.query_selector('div.home').inner_html())
        offers = self.get_offers()

        not_claimable_offers = [offer for offer in offers if offer.get(
            'linkedJourney') == None and offer.get('self') == None]
        external_offers = [
            offer for offer in offers if offer['deliveryMethod'] == 'EXTERNAL_OFFER' and offer not in not_claimable_offers and PrimeLooter.check_eligibility(offer)]
        direct_offers = [
            offer for offer in offers if offer['deliveryMethod'] == 'DIRECT_ENTITLEMENT' and PrimeLooter.check_eligibility(offer)]

        # list non claimable offers
        msg = "Can not claim these ingame offers:"
        for offer in not_claimable_offers:
            msg += f"\n    - {offer['title']}"
        msg = msg[:-1]
        log.info(msg)

        # claim direct offers
        if direct_offers:
            msg = "Claiming these direct offers:"
            for offer in direct_offers:
                msg += f"\n    - {offer['title']}"
            msg = msg[:-1]
            log.info(msg)
            self.claim_direct()
        else:
            log.info("No direct offers to Claim")

        # filter publishers
        if not 'all' in self.publishers:
            external_offers = [offer for offer in external_offers if offer['content']
                               ['publisher'] in self.publishers]

        # claim external offers
        if external_offers:
            msg = "Claiming these external offers:"
            for offer in external_offers:
                msg += f"\n    - {offer['title']}"
            msg = msg[:-1]
            log.info(msg)

            for offer in external_offers:
                try:
                    if PrimeLooter.check_eligibility(offer):
                        self.claim_external(
                            offer['content']['externalURL'], offer['content']['publisher'])
                except Exception as ex:
                    log.error(ex)
        else:
            log.info("No external offers to Claim")


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
                with PrimeLooter(cookies, publishers, headless) as looter:
                    log.info("start looting cycle")
                    looter.run(dump)
                    log.info("finished looting cycle")
            except Exception as ex:
                log.error("Error %s", ex)
                traceback.print_tb(ex.__traceback__)
                time.sleep(60)
                continue
            time.sleep(60*60*24)
    else:
        try:
            with PrimeLooter(cookies, publishers, headless) as looter:
                looter.run(dump)
        except Exception as ex:
            log.error("Error %s", ex)
            traceback.print_tb(ex.__traceback__)
            raise ex
 