import time as tm
from bs4 import BeautifulSoup


def collect_product_info(driver, url=""):
    driver.switch_to.new_window("tab")
    tm.sleep(3)
    driver.get(url=url)
    tm.sleep(3)

    soup = BeautifulSoup(driver.page_source, "lxml")

    product_name = soup.find("div", attrs={"data-widget": "webProductHeading"}).find("h1").text.strip()

    try:
        ozon_card_price_element = soup.find("span", string="c Ozon Картой").parent.find("div").find("span")
        product_ozon_card_price = ozon_card_price_element.text.strip() if ozon_card_price_element else None

        price_element = soup.find("span", string="без Ozon Карты").parent.parent.find("div").findAll("span")
        product_discount_price = price_element[0].text.strip() if price_element else None
    except:
        product_ozon_card_price = None
        product_discount_price = None

    product_data = {
        "product_name": product_name,
        "product_ozon_card_price": product_ozon_card_price,
        "product_discount_price": product_discount_price,
        "url": url,
    }
    return product_data
