import argparse
import http.cookiejar as cookiejar
import logging
import sys
import time
import traceback
import json
import typing

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Cookie, Error, Page

handler = logging.StreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    # format="%(asctime)s [%(levelname)s] %(msg)s",
    format="{asctime} [{levelname}] {message}",
    style='{',
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler("primelooter.log"), handler],
)

log = logging.getLogger()


class AuthException(Exception):
    pass


class PrimeLooter:
    def __init__(self, cookies, publishers="all", headless=True, use_chrome=True):
        self.cookies = cookies
        self.publishers = publishers
        self.headless = headless
        self.use_chrome = use_chrome

    def __enter__(self):
        self.playwright = sync_playwright()

        if self.use_chrome:
            self.browser: Browser = self.playwright.start().chromium.launch(headless=self.headless)
        else:
            self.browser: Browser = self.playwright.start().firefox.launch(headless=self.headless)

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
    def code_to_file(game: str, code: str, instructions: str, seperator_string: str = "") -> None:
        seperator_string = seperator_string or "========================\n========================"
        with open("./game_codes.txt", "a") as f:
            f.write(f"{game}: {code}\n\n{instructions.replace('/n',' ')}\n{seperator_string}\n")

    @staticmethod
    def exists(tab: Page, selector: str) -> bool:
        if tab.query_selector(selector):
            return True
        return False

    def auth(self) -> None:
        with self.page.expect_response(
            lambda response: "https://gaming.amazon.com/graphql" in response.url
            and "currentUser" in response.json()["data"]
        ) as response_info:
            log.debug("get auth info")
            self.page.goto("https://gaming.amazon.com/home")
            response = response_info.value.json()["data"]["currentUser"]
            if not response["isSignedIn"]:
                raise AuthException("Authentication: Not signed in. (Please recreate the cookie.txt file)")
            elif not response["isAmazonPrime"]:
                raise AuthException(
                    "Authentication: Not a valid Amazon Prime account. "
                    "(Loot can only be redeemed with an Amazon Prime Membership)"
                )
            elif not response["isTwitchPrime"]:
                raise AuthException(
                    "Authentication: Not a valid Twitch Prime account. "
                    "(Loot can only be redeemed with an Amazon Prime subscription and a connected Twitch Prime account)"
                )

    def get_offers(self) -> typing.List:
        with self.page.expect_response(
            lambda response: "https://gaming.amazon.com/graphql" in response.url
            and "primeOffers" in response.json()["data"]
        ) as response_info:
            log.debug("get offers")
            self.page.goto("https://gaming.amazon.com/home")
            return response_info.value.json()["data"]["primeOffers"]

    @staticmethod
    def check_eligibility(offer: dict) -> bool:
        if offer["linkedJourney"]:
            for suboffer in offer["linkedJourney"]["offers"]:
                if suboffer["self"]["eligibility"]:
                    if suboffer["self"]["eligibility"]["canClaim"]:
                        return True
            return False
        if offer["self"]:
            return offer["self"]["eligibility"]["canClaim"]
        raise Exception(f"Could not check offer eligibility status\n{json.dumps(offer, indent=4)}")

    @staticmethod
    def check_claim_status(offer: dict) -> bool:
        if offer["linkedJourney"]:
            for suboffer in offer["linkedJourney"]["offers"]:
                if suboffer["self"]["eligibility"]:
                    if suboffer["self"]["eligibility"]["isClaimed"]:
                        return True
            return False
        if offer["self"]:
            return offer["self"]["eligibility"]["isClaimed"]
        raise Exception(f"Could not check offer eligibility status\n{json.dumps(offer, indent=4)}")

    def claim_external(self, url, publisher):
        tab = self.context.new_page()
        try:
            with tab.expect_response(
                lambda response: "https://gaming.amazon.com/graphql" in response.url
                and "journey" in response.json()["data"]
            ) as response_info:
                log.debug("get game title")
                tab.goto(url)
                game_name = response_info.value.json()["data"]["journey"]["assets"]["title"]

            log.debug(f"Try to claim {game_name} from {publisher}")
            tab.wait_for_selector("div[data-a-target=loot-card-available]")

            loot_cards = tab.query_selector_all("div[data-a-target=loot-card-available]")

            for loot_card in loot_cards:
                loot_name = loot_card.query_selector("h3[data-a-target=LootCardSubtitle]").text_content()
                log.debug(f"Try to claim loot {loot_name} from {game_name} by {publisher}")

                claim_button = loot_card.query_selector("button[data-test-selector=AvailableButton]")
                if not claim_button:
                    log.warning(f"Could not claim {loot_name} from {game_name} by {publisher} (in-game loot)")
                    continue

                claim_button.click()
                tab.wait_for_load_state("networkidle")

                # validate
                tab.wait_for_selector("div[data-a-target=gms-base-modal]")

                if PrimeLooter.exists(tab, "div.gms-success-modal-container"):
                    log.info(f"Claimed {loot_name} ({game_name})")

                    if PrimeLooter.exists(tab, "div.get-my-stuff-modal-code-success"):
                        try:
                            code = (
                                tab.query_selector(
                                    'div.get-my-stuff-modal-code div[data-a-target="copy-code-input"] input'
                                )
                                .get_attribute("value")
                                .strip()
                            )
                            instructions = (
                                tab.query_selector("div[data-a-target=gms-claim-instructions]").inner_text().strip()
                            )
                            PrimeLooter.code_to_file(game_name, code, instructions)
                        except Exception:
                            log.warning(f"Could not get code for {loot_name} ({game_name}) from {publisher}")

                elif PrimeLooter.exists(tab, "div[data-test-selector=ProgressBarSection]"):
                    log.warning(f"Could not claim {loot_name} from {game_name} by {publisher} (account not connected)")
                else:
                    log.warning(f"Could not claim {loot_name} from {game_name} by {publisher} (unknown error)")
                if tab.query_selector("button[data-a-target=close-modal-button]"):
                    tab.query_selector("button[data-a-target=close-modal-button]").click()
        except Error as ex:
            print(ex)
            traceback.print_tb(ex.__traceback__)
            log.error(
                f"An error occured ({publisher}/{game_name})! Did they make some changes to the website? "
                "Please report @github if this happens multiple times."
            )
        finally:
            tab.close()

    def claim_direct(self):
        tab = self.context.new_page()
        try:
            tab.goto("https://gaming.amazon.com/home")

            fgwp_xpath = 'xpath=//button[@data-a-target="FGWPOffer"]/ancestor::div[@data-test-selector="Offer"]'

            elements = self.page.query_selector_all(fgwp_xpath)

            if len(elements) == 0:
                log.error(
                    "No direct offers found! Did they make some changes to the website? "
                    "Please report @github if this happens multiple times."
                )

            for elem in elements:
                elem.scroll_into_view_if_needed()
                self.page.wait_for_load_state("networkidle")

                game_name = elem.query_selector("h3").text_content()

                try:
                    publisher = elem.query_selector("p.tw-c-text-alt-2").text_content()
                except AttributeError:
                    log.error(f"Cannot claim {game_name}...")
                    continue

                log.debug(f"Try to claim {game_name} by {publisher}")
                elem.query_selector("button[data-a-target=FGWPOffer]").click()
                log.info(f"Claimed {game_name} by {publisher}")
        except Error as ex:
            log.error(ex)
            traceback.print_tb(ex.__traceback__)
        finally:
            tab.close()

    def run(self, dump: bool = False):
        self.auth()

        if dump:
            print(self.page.query_selector("div.home").inner_html())
        offers = self.get_offers()

        not_claimable_offers = [
            offer for offer in offers if offer.get("linkedJourney") is None and offer.get("self") is None
        ]
        claimed_offers = [
            offer for offer in offers if offer not in not_claimable_offers and PrimeLooter.check_claim_status(offer)
        ]
        external_offers = [
            offer
            for offer in offers
            if offer["deliveryMethod"] == "EXTERNAL_OFFER"
            and offer not in not_claimable_offers
            and PrimeLooter.check_eligibility(offer)
        ]
        direct_offers = [
            offer
            for offer in offers
            if offer["deliveryMethod"] == "DIRECT_ENTITLEMENT" and PrimeLooter.check_eligibility(offer)
        ]

        # list non claimable offers
        msg = "Can not claim these ingame offers:"
        for offer in not_claimable_offers:
            msg += f"\n    - {offer['title']}"
        msg = msg[:-1]
        msg += "\n"
        log.info(msg)

        # list claimed offers
        msg = "The following offers have been claimed already:"
        for offer in claimed_offers:
            msg += f"\n    - {offer['title']}"
        msg = msg[:-1]
        msg += "\n"
        log.info(msg)

        # claim direct offers
        if direct_offers:
            msg = "Claiming these direct offers:"
            for offer in direct_offers:
                msg += f"\n    - {offer['title']}"
            msg = msg[:-1]
            msg += "\n"
            log.info(msg)
            self.claim_direct()
        else:
            log.info("No direct offers to claim\n")

        # filter publishers
        if "all" not in self.publishers:
            external_offers = [offer for offer in external_offers if offer["content"]["publisher"] in self.publishers]

        # claim external offers
        if external_offers:
            msg = "Claiming these external offers:"
            for offer in external_offers:
                msg += f"\n    - {offer['title']}"
            msg = msg[:-1]
            msg += "\n"
            log.info(msg)

            for offer in external_offers:
                self.claim_external(offer["content"]["externalURL"], offer["content"]["publisher"])
        else:
            log.info("No external offers to claim\n")


def read_cookiefile(path: str) -> typing.List[Cookie]:
    jar = cookiejar.MozillaCookieJar(path)
    jar.load()

    _cookies: typing.List[Cookie] = list()

    for _c in jar:
        cookie = Cookie(
            name=_c.name, value=_c.value, domain=_c.domain, path=_c.path, expires=_c.expires, secure=_c.secure
        )
        _cookies.append(cookie)
    return _cookies


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Notification bot for the lower saxony vaccination portal")

    parser.add_argument(
        "-p",
        "--publishers",
        dest="publishers",
        help="Path to publishers.txt file",
        required=False,
        default="publishers.txt",
    )
    parser.add_argument(
        "-c", "--cookies", dest="cookies", help="Path to cookies.txt file", required=False, default="cookies.txt"
    )
    parser.add_argument(
        "-l",
        "--loop",
        dest="loop",
        help="Shall the script loop itself? (Cooldown 24h)",
        required=False,
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "--dump", dest="dump", help="Dump html to output", required=False, action="store_true", default=False
    )

    parser.add_argument(
        "-d",
        "--debug",
        dest="debug",
        help="Print Log at debug level",
        required=False,
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "-nh",
        "--no-headless",
        dest="headless",
        help="Shall the script not use headless mode?",
        required=False,
        action="store_false",
        default=True,
    )

    arg = vars(parser.parse_args())

    cookies = read_cookiefile(arg["cookies"])

    with open(arg["publishers"]) as f:
        publishers = f.readlines()
    publishers = [x.strip() for x in publishers]
    headless = arg["headless"]
    dump = arg["dump"]

    if arg["debug"]:
        log.level = logging.DEBUG

    with PrimeLooter(cookies, publishers, headless) as looter:
        while True:
            try:
                log.info("Starting Prime Looter\n")
                looter.run(dump)
                log.info("Finished Looting!\n")
            except AuthException as ex:
                log.error(ex)
                sys.exit(1)
            except Exception as ex:
                log.error(ex)
                traceback.print_tb(ex.__traceback__)
                time.sleep(60)
            else:
                handler.terminator = "\r"

                sleep_time = 60 * 60 * 24
                for time_slept in range(sleep_time):
                    m, s = divmod(sleep_time - time_slept, 60)
                    h, m = divmod(m, 60)
                    log.info(f"{h:d}:{m:02d}:{s:02d} till next run...")
                    time.sleep(1)

                handler.terminator = "\n"

            if not arg["loop"]:
                break
