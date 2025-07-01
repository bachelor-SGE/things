import tkinter as tk
import pyautogui
import pytesseract
import csv
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait

# Указываем путь к Tesseract (если не добавлен в PATH)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Конфигурации для OCR:
# Для зон с ценами – разрешаем цифры, знаки, % и буквы для обозначения "млрд"/"млн"
CONFIG_PRICE = "--psm 6 -c tessedit_char_whitelist=0123456789.,%млрдМЛРДмлнМЛНmnpzaAMNPZDLITERXVBNa"
# Для зон с лотами – разрешаем только цифры
CONFIG_NUMBERS = "--psm 6 -c tessedit_char_whitelist=0123456789.,%млрдМЛРДмлнМЛНmnpzaAMNPZDLITERXVBN"

# Статический список тикеров (без префикса)
TICKERS = [
    # А
    "ABRD", "AFKS", "AFLT", "AGRO", "AKRN", "ALRS", "AMEZ", "APTK", "ARMD",
    "ARSA", "ASSB", "AVAN", "AVAZ", "AVAZP", "IMOEXF",
    # Б
    "BANEP", "BELU", "BSPB", "BSPBP",
    # В
    "VJGZ", "VLHZ", "VRSB", "VSMO",
    # Г
    "GAZP", "GAZP02", "GAZP03", "GAZP04",
    # Д
    "DALM", "DALMP", "DIOD", "DSKY", "DZRDP",
    # Е
    "ENRU", "EPLN", "ERCO", "ETLN",
    # Ж
    "NKNC", "NKSH",  # (Ж - отсутствуют прямые тикеры на букву Ж, тут пример с НКНХ)
    # З
    "ZILL", "ZVEZ",
    # И
    "IRAO", "IRGZ",
    # К
    "KAZT", "KBTK", "KMAZ", "KMEZ", "KOGK", "KRKN", "KRKNP", "KROT", "KRSB", "KRSBP",
    # Л
    "LSNG", "LSNGP", "LSRG", "LKOH", "LNTA", "LNZL", "LNZLP",
    # М
    "MAGN", "MFGS", "MFON", "MGNT", "MGNZ", "MGTS", "MGTS-p", "MGTSP", "MISM", "MOEX", "MORI", "MSNG", "MSRS", "MSTT", "MTLR", "MTLRP", "MTSS", "MVID",
    # Н
    "NFAZ", "NKHP", "NKNC", "NKNCP", "NLMK", "NMTP", "NNSB", "NNSBP", "NPOF", "NSVZ", "NTBN", "NVTR",
    # О
    "OBUV", "ODVA", "OFCB", "OGKB", "OJSB", "OMZZP", "OPIN", "OSMP", "OTCP",
    # П
    "PAZA", "PHOR", "PIKK", "PLZL", "PMSBP", "POLY", "PRFN", "PRIM", "PRIN", "PRMB", "PSBR", "QIWI",
    # Р
    "RASP", "RBCM", "RKKE", "RLMN", "RLMNP", "RNAV", "ROLO", "ROSB", "ROSN", "RSTI", "RSTIP", "RTGZ", "RUAL", "RUSP", "RZSB",
    # С
    "SARE", "SAREP", "SBER", "SBERP", "SELG", "SFIN", "SGZH", "SKBK", "SKBKP", "SLEN", "SMLT", "SNGS", "SNGSP", "SPBE", "STSB", "STSBP", "SVAV", "SYNG",
    # Т
    "TANL", "TANLP", "TASB", "TASBP", "TATN", "TATNP", "TGKA", "TGKB", "TGKC", "TGKD", "TNBP", "TNBPP", "TRCN", "TRMK", "TRNFP", "TTLK", "TUZA", "TVGR",
    # У
    "UCSS", "UKUZ", "UNAC", "UNKL", "UPRO", "URFD", "URKA", "URKZ", "URSI", "URSIP", "UWGN", "UZPS",
    # Ф
    "FESH", "FEES", "FLOT",
    # Х
    "HALS", "HIMC", "HIMCP",
    # Ц
    "CNTL", "CNTLP",
    # Ч
    "CHEP", "CHGZ", "CHMK", "CHZN",
    # Ш
    "SHBZ",
    # Щ (нет акций на Щ)
    # Э
    "EONR", "ELTZ", 
    # Ю
    "YAKG", 
    # Я
    "YNDX", 
]

# Имена полей для OCR (7 критериев)
FIELD_NAMES = ["volume", "max_price", "min_price", "open_price", "turnover", "day_range", "avg_volume"]

# Глобальное хранилище выбранных областей: для каждого поля будет сохранён кортеж (x, y, width, height)
region_data = {field: None for field in FIELD_NAMES}

# -----------------------------------------------------------------------------
# Класс для графического выбора области (полноэкранный оверлей)
# -----------------------------------------------------------------------------
class ScreenSelector(tk.Toplevel):
    """
    Открывает полноэкранное окно для выбора области экрана.
    Пользователь выделяет прямоугольник мышью, после чего вызывается callback с координатами (x, y, width, height).
    """
    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.rect = None

        self.overrideredirect(True)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}+0+0")

        try:
            self.attributes("-alpha", 0.3)
        except Exception as e:
            print("Атрибут прозрачности не поддерживается:", e)

        self.config(bg="black")
        self.canvas = tk.Canvas(self, cursor="cross", bg="black")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y,
                                                   outline="red", width=2)

    def on_mouse_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_button_release(self, event):
        end_x, end_y = event.x, event.y
        x = min(self.start_x, end_x)
        y = min(self.start_y, end_y)
        width = abs(end_x - self.start_x)
        height = abs(end_y - self.start_y)
        self.callback(x, y, width, height)
        self.destroy()

# -----------------------------------------------------------------------------
# Функция для выбора области через ScreenSelector
# -----------------------------------------------------------------------------
def select_region_gui(field):
    """
    Открывает полноэкранное окно для выбора области и сохраняет координаты в region_data[field].
    """
    def callback(x, y, width, height):
        region_data[field] = (x, y, width, height)
        print(f"Область для '{field}' выбрана: {region_data[field]}")
    selector = ScreenSelector(callback)
    selector.focus_set()
    selector.mainloop()

# -----------------------------------------------------------------------------
# Инициализация Selenium
# -----------------------------------------------------------------------------
def init_driver():
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)
    driver.maximize_window()  # рекомендуется для стабильности координат
    return driver

# -----------------------------------------------------------------------------
# Функция навигации по тикерам через Selenium
# -----------------------------------------------------------------------------
def navigate_to_ticker(driver, ticker):
    """
    С помощью Selenium переходим на страницу тикера.
    Формат URL: https://trading.finam.ru/profile/MOEX-{тикер}
    """
    url = f"https://trading.finam.ru/profile/MOEX-{ticker}"
    print(f"Переход по URL: {url}")
    driver.get(url)
    time.sleep(3)  # время на загрузку страницы

# -----------------------------------------------------------------------------
# Функция OCR для выбранной области с конфигурацией
# -----------------------------------------------------------------------------
def ocr_region(region, config=""):
    """
    Делает скриншот области (region = (x, y, width, height)) и возвращает распознанный текст через Tesseract.
    """
    screenshot = pyautogui.screenshot(region=region)
    text = pytesseract.image_to_string(screenshot, lang="eng", config=config)
    return text.strip()

# -----------------------------------------------------------------------------
# Основной процесс: перебор тикеров, OCR по выбранным областям, сохранение в CSV
# -----------------------------------------------------------------------------
def start_process():
    # Проверяем, что все области выбраны
    missing = [field for field, reg in region_data.items() if reg is None]
    if missing:
        print("Не выбраны области для:", missing)
        return
    
    driver = init_driver()
    results = []
    for ticker in TICKERS:
        print(f"\nОбрабатываем тикер: {ticker}")
        navigate_to_ticker(driver, ticker)
        row = {"ticker": ticker}
        for field in FIELD_NAMES:
            reg = region_data[field]
            # Если поле volume – используем конфигурацию для чисел, иначе для цен
            config = CONFIG_NUMBERS if field == "volume" else CONFIG_PRICE
            value = ocr_region(reg, config=config)
            row[field] = value
            print(f"  {field}: {value}")
        results.append(row)
        time.sleep(1)
    driver.quit()

    # Сохраняем результаты в CSV
    csv_fields = ["ticker"] + FIELD_NAMES
    with open("finam_data.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for r in results:
            writer.writerow(r)
    
    print("\nСбор данных завершен! Результаты сохранены в 'finam_data.csv'.")

# -----------------------------------------------------------------------------
# Построение главного окна GUI
# -----------------------------------------------------------------------------
def build_gui():
    root = tk.Tk()
    root.title("Finam Selenium + Tesseract Bot")

    row = 0

    # Инструкция
    lbl = tk.Label(root, text="Сначала выберите области для каждого критерия, затем нажмите 'Старт!'\n"
                                "Окно выбора области появится на весь экран. Для выбора - мышью выделите нужный прямоугольник.")
    lbl.grid(row=row, column=0, padx=10, pady=5, sticky="w")
    row += 1

    # Кнопки для выбора областей для каждого из 7 критериев
    for field in FIELD_NAMES:
        btn = tk.Button(root, text=f"Выбрать область для {field}", command=lambda f=field: select_region_gui(f))
        btn.grid(row=row, column=0, padx=10, pady=5, sticky="w")
        row += 1

    # Кнопка "Старт!"
    btn_start = tk.Button(root, text="Старт!", command=start_process, bg="green", fg="white")
    btn_start.grid(row=row, column=0, padx=10, pady=10, sticky="w")

    root.resizable(False, False)
    return root

def main():
    app = build_gui()
    app.mainloop()

if __name__ == "__main__":
    main()

