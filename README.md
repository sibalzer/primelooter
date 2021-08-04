# [WIP] Primelooter

![GitHub tag (latest by date)](https://img.shields.io/github/v/tag/sibalzer/primelooter?label=version)
[![Python](https://img.shields.io/badge/Made%20with-Python%203.x-blue.svg?style=flat-square&logo=Python&logoColor=white)](https://www.python.org/)
[![GitHub license](https://img.shields.io/github/license/sibalzer/impfbot)](https://github.com/sibalzer/primelooter/blob/main/LICENSE)

python bot which claims twitch prime gaming loot

still wip (not fully tested)

## Usage

### 1. ⚙️ General Setup

#### Local 📌

1.  Install python3
2.  Install package requirements: `$> pip install -r requirements.txt`
3.  Install playwright: `$> python -m playwright install`
4.  Create your own cookies.txt and publishers.txt (see example files)

#### Docker 🐳

If you want to use the provided docker image (only linux/amd64 plattform for now) you must mount the **config.txt** and **providers.txt** into the **/app** path. (example compose file is provided)

### 2. 🍪 Generate a cookie.txt (Firefox)

1.  Install this addon: [cookie.txt](https://addons.mozilla.org/de/firefox/addon/cookies-txt/)
2.  Goto: [https://gaming.amazon.com](https://gaming.amazon.com)
3.  Login with your credentials
4.  There should be a new add-on icon in the right corner. Click on it and Export Cookies->Current Site

(Be careful not to share your cookie.txt! Keep it a secret like your credentials)

### 3. 🏢 Create a publishers.txt

Create a publishers.txt like the example file. Each line represents the publisher name used on the [https://gaming.amazon.com](https://gaming.amazon.com) website.

### 4. 🏃 Run

The script offers multiple arguments:

- -c | --cookie: Path to cookies.txt file
- -p | --publishers: Path to publishers.txt file
- -l | --loop: loops the script with a cooldown of 24h
- -nh | --no-headless: starts the script with a visible browser (mainly for debugging)

If you use docker simply start the container.

If you want to use cron.d instead of letting the script wait 24h you must create a new file under `/etc/cron.d`. Example:

`0 0 * * * root : Primelooter ; /usr/bin/python3 /path/to/primelooter.py --cookie /path/to/cookie.txt --publishers /path/to/publishers.txt`

<a href='https://ko-fi.com/balzer' target='_blank'><img height='35' style='border:0px;height:46px;' src='https://az743702.vo.msecnd.net/cdn/kofi3.png?v=0' border='0' alt='Buy Me a Coffee at ko-fi.com' />
