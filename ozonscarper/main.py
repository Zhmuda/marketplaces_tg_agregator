import sqlite3
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from .functions import collect_product_info


def get_products_links(item_name="наушники hyperx"):
    driver = uc.Chrome()
    driver.implicitly_wait(5)

    driver.get(url="https://ozon.ru")
    time.sleep(2)

    find_input = driver.find_element(By.NAME, "text")
    find_input.clear()
    find_input.send_keys(item_name)
    time.sleep(2)

    find_input.send_keys(Keys.ENTER)
    time.sleep(2)

    current_url = f"{driver.current_url}&sorting=rating"
    driver.get(url=current_url)
    time.sleep(2)

    try:
        find_links = driver.find_elements(By.CLASS_NAME, "tile-hover-target")
        products_urls = list(set([f"{link.get_attribute('href')}" for link in find_links]))
    except Exception as e:
        print(f"[!] Ошибка при сборе ссылок: {e}")
        return []

    products = []
    for url in products_urls[:2]:  # Лимит на два товара
        product_data = collect_product_info(driver=driver, url=url)
        products.append(product_data)

    driver.close()
    driver.quit()
    return products
