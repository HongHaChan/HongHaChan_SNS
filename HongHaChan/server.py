from flask import Flask, jsonify, render_template, request, make_response
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from flask_cors import CORS, cross_origin
import time
import json
import pickle
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PIL import Image
import os
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from threading import Thread, Lock
import threading
import dateutil.parser
import schedule
import urllib
from urllib.request import urlopen
import codecs

app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})

taskThreadList = []

savePathName = "DataCollections/"

def pendingSchedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

pendingThread = Thread(name="pendingThread", target=pendingSchedule)
pendingThread.start()

#path = "server.py"
#cmd2 =  'schtasks /create /tn chanhariServer /sc onlogon /tr '+path
#os.system(cmd2)

def fullpage_screenshot(driver, file):
    print("Starting chrome full page screenshot workaround ...")

    total_width = driver.execute_script("return document.body.offsetWidth")
    total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
    viewport_width = driver.execute_script("return document.body.clientWidth")
    viewport_height = driver.execute_script("return window.innerHeight")
    print("Total: ({0}, {1}), Viewport: ({2},{3})".format(total_width, total_height, viewport_width, viewport_height))
    rectangles = []

    i = 0
    while i < total_height:
        ii = 0
        top_height = i + viewport_height

        if top_height > total_height:
            top_height = total_height

        while ii < total_width:
            top_width = ii + viewport_width

            if top_width > total_width:
                top_width = total_width

            print("Appending rectangle ({0},{1},{2},{3})".format(ii, i, top_width, top_height))
            rectangles.append((ii, i, top_width, top_height))

            ii = ii + viewport_width

        i = i + viewport_height

    stitched_image = Image.new('RGB', (total_width, total_height))
    previous = None
    part = 0

    for rectangle in rectangles:
        if not previous is None:
            driver.execute_script("window.scrollTo({0}, {1})".format(rectangle[0], rectangle[1]))
            print("Scrolled To ({0},{1})".format(rectangle[0], rectangle[1]))
            time.sleep(0.2)

        file_name = "part_{0}.png".format(part)
        print("Capturing {0} ...".format(file_name))

        driver.get_screenshot_as_file(file_name)
        screenshot = Image.open(file_name)

        if rectangle[1] + viewport_height > total_height:
            offset = (rectangle[0], total_height - viewport_height)
        else:
            offset = (rectangle[0], rectangle[1])

        print("Adding to stitched image with offset ({0}, {1})".format(offset[0], offset[1]))
        stitched_image.paste(screenshot, offset)

        del screenshot
        os.remove(file_name)
        part = part + 1
        previous = rectangle

    stitched_image.save(file)
    print("Finishing chrome full page screenshot workaround...")
    return True


def waitForElement(driver, xpath):
    timeout = 5
    try:
        element_present = EC.presence_of_element_located((By.XPATH, xpath))
        WebDriverWait(driver, timeout).until(element_present)
    except TimeoutException:
        errorMessage = "TimeoutException & No Such Element"
        print(errorMessage)


def connectUrl(driver, xpath, contents):
    driver.get(contents[0])


def inputText(driver, xpath, contents):
    splitPath = "//" + xpath.split('/')[-2] + "/" + xpath.split('/')[-1]
    waitForElement(driver, splitPath)
    driver.find_element_by_xpath(splitPath).send_keys(contents[0])
    return "inputText"

def inputEnter(driver, xpath, contents):
    splitPath = "//" + xpath.split('/')[-2] + "/" + xpath.split('/')[-1]
    #waitForElement(driver, splitPath)
    time.sleep(1)
    driver.find_element_by_xpath(splitPath).send_keys(Keys.RETURN)
    return "inputEnter"



def clickButton(driver, xpath, contents):
    splitPath = "//" + xpath.split('/')[-2] + "/" + xpath.split('/')[-1]
    waitForElement(driver, splitPath)
    driver.find_element_by_xpath(splitPath).click()
    return "clickButton"


def drawImage(driver, element, saveName):
    location = element.location
    size = element.size

    screenshotName = "Screenshot" + threading.current_thread().getName() + ".png"
    fullpage_screenshot(driver, screenshotName)
    # driver.save_screenshot('screenshot.png')
    # time.sleep(2)
    im = Image.open(screenshotName)
    left = location['x']
    top = location['y']
    right = location['x'] + size['width']
    bottom = location['y'] + size['height']

    im = im.crop((int(left), int(top), int(right), int(bottom)))
    im.save(saveName)


def drawCanvas(driver, element, saveName, canv):
    drawImage(driver, element, 'pdfTemp.png')
    canv.drawImage('pdfTemp.png', 0, 0)


def onCrawling(driver, xpath, contents):
    splitPath = "//" + xpath.split('/')[-2] + "/" + xpath.split('/')[-1]
    imagePath = "//" + xpath.split('/')[-4] + "/" + xpath.split('/')[-3] + "/" + xpath.split('/')[-2]

    if (contents[0] == "PICKLE"):
        waitForElement(driver, splitPath)
        targetData = driver.find_element_by_xpath(splitPath).text
        with open(contents[1], 'wb') as f:
            pickle.dump(targetData, f)

    elif (contents[0] == "JSON"):
        waitForElement(driver, splitPath)
        targetData = driver.find_element_by_xpath(splitPath).text
        with open(contents[1], 'w') as f:
            json.dump(targetData, f, ensure_ascii=False)

    elif (contents[0] == "TXT"):
        waitForElement(driver, splitPath)
        targetData = driver.find_element_by_xpath(splitPath).text
        f = open(contents[1], 'w+')
        f.write(targetData)
        f.close()

    elif (contents[0] == "PNG"):
        print("[PNG]")
        # png = driver.get_screenshot_as_png()
        # open(contents[1], "wb").write(png)
        waitForElement(driver, imagePath)
        element = driver.find_element_by_xpath(imagePath)
        drawImage(driver, element, contents[1])

    elif (contents[0] == "PDF"):
        waitForElement(driver, imagePath)
        element = driver.find_element_by_xpath(imagePath)
        canv = canvas.Canvas(contents[1], pagesize=A4)
        drawCanvas(driver, element, contents[1], canv)
        canv.save()

    elif(contents[0] == "VIDEO"):
        videoUrl = contents[2]
        yougetCommand = '';
        if os.name == "posix":  # OS가 Unix계열일 경우 (MacOS 포함)
            yougetCommand = 'LC_CTYPE=en_US.UTF-8 && you-get ' + videoUrl
        else:  # OS가 windows일 경우
            yougetCommand = 'chcp 65001 && you-get ' + videoUrl
        os.system(yougetCommand)

    return "onCrawling"


def isNumber(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def onIf(driver, xpath, contents, data, index, listIf):
    # targetValue = driver.find_element_by_xpath(xpath).get_attribute("text")
    waitForElement(driver, xpath)
    targetValue = driver.find_element_by_xpath(xpath).text
    targetValue = targetValue.strip()
    if(contents[0][0:1] == "!="):
        contentsValue = contents[0][2:]
    else:
        contentsValue = contents[0][1:]

    if (isNumber(targetValue)):
        targetValue = float(targetValue)
    if (isNumber(contentsValue)):
        contentsValue = float(contentsValue)

    if (contents[0][0] == ">"):
        if (targetValue > contentsValue):
            print(">>>>>>>>>>> true")
            return 1
        else:
            print(">>>>>>>>>>> false")
            return 2
    elif (contents[0][0] == "<"):
        if (targetValue < contentsValue):
            print("<<<<<<<<<<< true")
            return 1
        else:
            print("<<<<<<<<<<< false")
            return 2
    elif (contents[0][0] == "="):
        if (targetValue == contentsValue):
            print("========== true")
            return 1
        else:
            print("========== false")
            return 2
    elif (contents[0][0:2] == "!="):
        if (targetValue != contentsValue):
            print("!=!=!=!=!=!= true")
            return 1
        else:
            print("!=!=!=!=!=!= false")
            return 2

    return 3


def onElse(driver, xpath, contents, data, index, listIf, determineIf):
    return 0

def onFor(driver, xpath, contents, data, index, listFor):
    indexOfFor = int(data[index]['contents'][0])
    curFor = listFor.pop(0)
    addrOfFor = int(curFor[0])
    addrOfForEnd = int(curFor[1])

    for i in range(indexOfFor):
        for j in range(addrOfFor + 1, addrOfForEnd):
            listLen = len(data[j]['contents'][0].split(','))
            if (listLen == 1) | (data[j]['command'] != "INPUT") :
                commandFunc.get(data[j]['command'])(driver, data[j]['xpath'], data[j]['contents'])
            else:
                if i >= listLen:
                    commandFunc.get(data[j]['command'])(driver, data[j]['xpath'], [data[j]['contents'][0].split(',').pop()])
                else:
                    commandFunc.get(data[j]['command'])(driver, data[j]['xpath'], [data[j]['contents'][0].split(',')[i]])

    return addrOfForEnd


def onEnd(driver, xpath, contents):
    return "onEnd"

commandFunc = {
    "URL": connectUrl,
    "INPUT": inputText,
    "ENTER": inputEnter,
    "CLICK": clickButton,
    "CRAWLING": onCrawling,
    "IF": onIf,
    "ELIF": onIf,
    "ELSE": onElse,
    "END": onEnd,
    "FOR": onFor
}


def runTask(args):
    try:
        print(args[0])
        data = args[0]["actions"]
        loopCount = args[0]["loopCount"]
    except:
        data = args["actions"]
        loopCount = args["loopCount"]

    for curLoopCount in range(int(loopCount)):
        #TODO   Windows, UNIX 계열이외에 예외처리 필요
        if os.name == "posix":      # OS가 Unix계열일 경우 (MacOS 포함)
            driver = webdriver.Chrome(os.getcwd() + "/chromedriver")
        else:                       # OS가 windows일 경우
            driver = webdriver.Chrome("chromedriver.exe")

        driver.maximize_window()
        print(data)

        print("jool>>>>>>>>>>>")

        # For list
        listFor = []
        isList = False

        # If list
        listIf = [[[]]]
        isIf = False
        isElse = False
        ifCount = -1;
        ifInnerCount = 0;

        ### task1 pass-1        make list!
        for index in range(len(data)):
            tempCommand = data[index]['command']
            if (tempCommand == "FOR"):
                listFor.append([index, 0])
                isList = True
            elif (tempCommand == "IF"):
                ifCount += 1
                ifInnerCount = 0
                listIf.append([])
                listIf[ifCount].insert(ifInnerCount, ["IF", index, 0])
                isIf = True
            elif (tempCommand == "ELIF"):
                ifInnerCount += 1
                listIf[ifCount].insert(ifInnerCount, ["ELIF", index, 0])
                isIf = True
            elif (tempCommand == "ELSE"):
                ifInnerCount += 1
                listIf[ifCount].insert(ifInnerCount, ["ELSE", index, 0])
                isElse = True

            if ((tempCommand == "END") & (isList == True)):
                isList = False
                listFor[len(listFor) - 1][1] = index
            elif ((tempCommand == "END") & (isIf == True)):
                isIf = False
                listIf[ifCount][ifInnerCount][2] = index
            elif ((tempCommand == "END") & (isElse == True)):
                isElse = False
                listIf[ifCount][ifInnerCount][2] = index

        print('list for >> ')
        print(listFor)
        print('list for << ')
        print('list if >> ')
        print(listIf)
        print('list if << ')

        ### Task pass-2
        try:
            result = ""
            determineIf = 0     # 0: 판별전    1: True     2: False
            addrOfIfEnd = -1
            addrOfForEnd = -2

            for index in range(len(data)):
                ### Action 수행
                if data[index]['command'] == "FOR":
                    addrOfForEnd = commandFunc.get(data[index]['command'])(driver, data[index]['xpath'], data[index]['contents'], data, index, listFor)
                elif data[index]['command'] == "IF":
                    determineIf = commandFunc.get(data[index]['command'])(driver, data[index]['xpath'], data[index]['contents'], data, index, listIf)
                    if(determineIf == 1):   # True일 경우
                        listIf[0].pop(0)
                        addrOfIfEnd = -1
                        print("계속진행")
                        print(listIf)
                    elif(determineIf == 2):
                        addrOfIfEnd = listIf[0][0].pop(2)
                        listIf[0].pop(0)
                        print("End로 진행")
                        print(listIf)
                elif data[index]['command'] == "ELIF":
                    if (determineIf == 1):  # True일 경우
                        addrOfIfEnd = listIf[0][0].pop(2)
                        listIf[0].pop(0)
                        print("End로 진행")
                        print(listIf)
                    elif (determineIf == 2):
                        determineIf = commandFunc.get(data[index]['command'])(driver, data[index]['xpath'], data[index]['contents'], data, index, listIf)
                        if (determineIf == 1):  # True일 경우
                            listIf[0].pop(0)
                            print("계속진행")
                            print(listIf)
                        elif (determineIf == 2):
                            addrOfIfEnd = listIf[0][0].pop(2)
                            listIf[0].pop(0)
                            print("End로 진행")
                            print(listIf)

                elif data[index]['command'] == "ELSE":
                    commandFunc.get(data[index]['command'])(driver, data[index]['xpath'], data[index]['contents'], data, index, listIf, determineIf)
                    if (determineIf == 1):  # True일 경우
                        addrOfIfEnd = listIf[0][0].pop(2)
                        listIf[0].pop(0)
                        print("End로 진행")
                        print(listIf)
                    elif (determineIf == 2):
                        listIf[0].pop(0)
                        print("계속 진행")
                        print(listIf)
                else:
                    if index == addrOfIfEnd:
                        addrOfIfEnd = -1
                    if (addrOfIfEnd == -1) & (index > addrOfForEnd):
                        result = commandFunc.get(data[index]['command'])(driver, data[index]['xpath'], data[index]['contents'])

            print("endJool <<<<<<<<<<<<<<<<<<<<<<")

        except:
            return jsonify(resultCode=1)

def parsingTags(str):
    list = []

    start = 0
    idx = 0;
    i = 0
    while (i < len(str)):
        if start == 0 and str[i] == '#':
            start = 1
            idx = i
        elif start == 1:
            if str[i] == '#':
                list.append(str[idx:i])
                start = 0
                i = i - 1
            elif str[i] == ' ':
                list.append(str[idx:i])
                start = 0
            elif str[i] == '\n':
                list.append(str[idx:i])
                start = 0
            elif i == (len(str) - 1):
                list.append(str[idx:i + 1])
                start = 0
        i = i + 1

    return list

def runInstagram(args):

    pathName = savePathName+"instagram/"

    #directory 없다면 생성한다.
    if not os.path.exists(pathName):
        os.makedirs(pathName)

    tags = args["tags"]
    formatCount = args["format"]["count"]
    formatType = args["format"]["type"]

    if os.name == "posix":  # OS가 Unix계열일 경우 (MacOS 포함)
        driver = webdriver.Chrome(os.getcwd() + "/chromedriver")
    else:  # OS가 windows일 경우
        driver = webdriver.Chrome("chromedriver.exe")

    time.sleep(0.5)
    driver.maximize_window()
    driver.get("http://www.instagram.com")

    #Login Instagram
    waitForElement(driver,"//section/main/article/div[2]/div[2]/p/a")
    driver.find_element_by_xpath("//section/main/article/div[2]/div[2]/p/a").click()
    waitForElement(driver,"//*[@id='react-root']/section/main/article/div[2]/div[1]/div/form/div[1]/input")
    driver.find_element_by_xpath("//*[@id='react-root']/section/main/article/div[2]/div[1]/div/form/div[1]/input").send_keys("HongHaChan")
    waitForElement(driver,"//*[@id='react-root']/section/main/article/div[2]/div[1]/div/form/div[2]/input")
    driver.find_element_by_xpath("//*[@id='react-root']/section/main/article/div[2]/div[1]/div/form/div[2]/input").send_keys("1379555")
    waitForElement(driver,"//*[@id='react-root']/section/main/article/div[2]/div[1]/div/form/span/button")
    driver.find_element_by_xpath("//*[@id='react-root']/section/main/article/div[2]/div[1]/div/form/span/button").click()

    #Search Hashtag
    for curTag in tags:
        pathNameCurTag = pathName + "#" + curTag;
        if not os.path.exists(pathNameCurTag):
            os.makedirs(pathNameCurTag)

        waitForElement(driver,"//*[@id='react-root']/section/nav/div/div/div/div[2]/input")
        driver.find_element_by_xpath("//*[@id='react-root']/section/nav/div/div/div/div[2]/input").send_keys("#" + curTag)
        time.sleep(1)
        driver.find_element_by_xpath("//*[@id='react-root']/section/nav/div/div/div/div[2]/input").send_keys(Keys.RETURN)
        time.sleep(2)
        waitForElement(driver, "//*[@id='react-root']/section/main/article/div[2]/div[3]/a")
        driver.find_element_by_xpath("//*[@id='react-root']/section/main/article/div[2]/div[3]/a").click()
        time.sleep(1)

        while len(driver.find_elements_by_class_name("_jjzlb")) <= formatCount:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight-500);")
            time.sleep(0.2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight-1200);")
            time.sleep(0.2)

        elements = []
        elements = driver.find_elements_by_class_name("_jjzlb")
        del elements[formatCount:]

        #Save Text
        if (formatType[0] == 1):
            #f = open("#" + curTag + ".txt" , 'w+')
            f = codecs.open(pathNameCurTag + "/" + "#" + curTag + "(instagram)" + ".txt", "wb", "utf-8")

            for ele in elements:
                f.write(str(elements.index(ele)+1) + " ")
                curText = ele.find_element_by_xpath(".//*").get_attribute('alt')
                f.write(curText + "\r\r\n\r\r\n")
            f.close()

        #Save Image
        pathNameCurTagImg = pathNameCurTag+'/images';
        if not os.path.exists(pathNameCurTagImg):
            os.makedirs(pathNameCurTagImg)

        if(formatType[1] == 1):
            for ele in elements:
                img_url = ele.find_element_by_xpath(".//*").get_attribute('src')
                inputData = urlopen(img_url).read()

                downloaded_image = "/" + "#" + curTag + str(elements.index(ele)+1) + "(instagram)" + ".jpg"
                sf = open(pathNameCurTagImg+downloaded_image, "wb")
                sf.write(inputData)
                sf.close()

        if(formatType[2] == 1):
            dataList = []

            for ele in elements:
                curText = ele.find_element_by_xpath(".//*").get_attribute('alt')
                img_url = ele.find_element_by_xpath(".//*").get_attribute('src')
                eleTagList = parsingTags(curText)
                eleData = {
                    "content" : curText,
                    "image_url" : img_url,
                    "tags" : eleTagList
                }
                dataList.append(eleData)

            targetData = {
                "keyword": curTag,
                "count": formatCount,
                "data": dataList
            }
            with open(pathNameCurTag + "/" + "#" + curTag + "(instagram)" + '.json', 'w') as f:
                json.dump(targetData, f)  # 저정된 데이터는 다른 python 에서 실행이된다.

        print("[Instagram] #" + curTag + " End")

def runFacebook(args):
    pathName = savePathName+"facebook/"
    if not os.path.exists(pathName):
        os.makedirs(pathName)

    tags = args["tags"]
    formatCount = args["format"]["count"]
    formatType = args["format"]["type"]

    if os.name == "posix":  # OS가 Unix계열일 경우 (MacOS 포함)
        driver = webdriver.Chrome(os.getcwd() + "/chromedriver")
    else:  # OS가 windows일 경우
        driver = webdriver.Chrome("chromedriver.exe")

    time.sleep(0.5)
    driver.maximize_window()
    driver.get("http://www.facebook.com")

    #Login Facebook
    waitForElement(driver,'//*[@id="email"]')
    driver.find_element_by_xpath('//*[@id="email"]').send_keys('tjdghdrb2@naver.com')
    waitForElement(driver, '//*[@id="pass"]')
    driver.find_element_by_xpath('//*[@id="pass"]').send_keys('1379%%%')
    time.sleep(1)
    driver.find_element_by_xpath('//*[@id="pass"]').send_keys(Keys.RETURN)
    #waitForElement(driver, '//*[@id="u_0_p"]')
    #driver.find_element_by_xpath('//*[@id="u_0_p"]').click()

    #Exit Alert
    time.sleep(1)
    waitForElement(driver, '//*[@id="q"]')
    driver.find_element_by_xpath('//*[@id="q"]').send_keys(Keys.ESCAPE)
    time.sleep(1)

    #Search Tags
    for curTag in tags:
        pathNameCurTag = pathName + "#" + curTag;
        if not os.path.exists(pathNameCurTag):
            os.makedirs(pathNameCurTag)

        waitForElement(driver, '//*[@id="q"]')
        driver.find_element_by_xpath('//*[@id="q"]').send_keys("#" + curTag)
        time.sleep(1)
        driver.find_element_by_xpath('//*[@id="q"]').send_keys(Keys.RETURN)

        while len(driver.find_elements_by_class_name("_5pbx")) <= formatCount:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.2)

        # Save Text
        if (formatType[0] == 1):
            elements = []
            elements = driver.find_elements_by_class_name("_5pbx")
            del elements[formatCount:]

            f = codecs.open(pathNameCurTag + "/" + "#" + curTag + "(facebook)" + ".txt", "wb", "utf-8")
            for ele in elements:
                f.write(str(elements.index(ele) + 1) + " ")
                curText = ele.text
                curText = curText[0:len(curText)-5] #번역보기 자르기
                f.write(curText + "\r\r\n\r\r\n")
            f.close()

        # Save Image
        pathNameCurTagImg = pathNameCurTag+'/images';
        if not os.path.exists(pathNameCurTagImg):
            os.makedirs(pathNameCurTagImg)

        if (formatType[1] == 1):
            while len(driver.find_elements_by_class_name("_5cq3")) <= formatCount:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.2)

            elements = []
            elements = driver.find_elements_by_class_name('_5cq3')  #_2a2q
            del elements[formatCount:]

            for ele in elements:
                img_url = ele.find_element_by_xpath(".//*//*//*").get_attribute('src')
                inputData = urlopen(img_url).read()

                downloaded_image = "/" + "#" + curTag + str(elements.index(ele) + 1) + "(facebook)" + ".jpg"
                sf = open(pathNameCurTagImg + downloaded_image, "wb")
                sf.write(inputData)
                sf.close()

        if (formatType[2] == 1):
            while len(driver.find_elements_by_class_name('_1dwg')) <= formatCount:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.2)

            #text
            elements = []
            elements = driver.find_elements_by_class_name("_1dwg")
            del elements[formatCount:]

            dataList = []

            for ele in elements:
                #text
                curText = ele.find_element_by_class_name('_5pbx').text
                curText = curText[0:len(curText)-5] #번역보기 자르기
                eleTagList = parsingTags(curText)

                #image
                imgUrlList = []
                urlElementList = []
                urlElementList = ele.find_element_by_class_name('_3x-2').find_elements_by_xpath(".//*//*//*//*//*//*")

                for urlElement in urlElementList:
                    imgUrlList.append(urlElement.get_attribute('src'))

                eleData = {
                    "content": curText,
                    "image_url": imgUrlList,
                    "tags": eleTagList
                }
                dataList.append(eleData)

            targetData = {
                "keyword": curTag,
                "count": formatCount,
                "data": dataList
            }
            with open(pathNameCurTag+"/" + "#" + curTag + "(facebook)" + '.json', 'w') as f:
                json.dump(targetData, f)  # 저정된 데이터는 다른 python 에서 실행이된다.

        print("[Facebook] #" + curTag + " End")

def runTwitter(args):
    pathName = savePathName + "twitter/"
    if not os.path.exists(pathName):
        os.makedirs(pathName)

    tags = args["tags"]
    formatCount = args["format"]["count"]
    formatType = args["format"]["type"]

    if os.name == "posix":  # OS가 Unix계열일 경우 (MacOS 포함)
        driver = webdriver.Chrome(os.getcwd() + "/chromedriver")
    else:  # OS가 windows일 경우
        driver = webdriver.Chrome("chromedriver.exe")

    time.sleep(0.5)
    driver.maximize_window()
    driver.get("http://www.twitter.com")

    #Login
    waitForElement(driver, '//*[@id="doc"]/div[1]/div/div[1]/div[2]/a[3]')
    driver.find_element_by_xpath('//*[@id="doc"]/div[1]/div/div[1]/div[2]/a[3]').click()
    waitForElement(driver, '//*[@id="login-dialog-dialog"]/div[2]/div[2]/div[2]/form/div[1]/input')
    driver.find_element_by_xpath('//*[@id="login-dialog-dialog"]/div[2]/div[2]/div[2]/form/div[1]/input').send_keys('tjdghdrb2@naver.com')
    waitForElement(driver, '//*[@id="login-dialog-dialog"]/div[2]/div[2]/div[2]/form/div[2]/input')
    driver.find_element_by_xpath('//*[@id="login-dialog-dialog"]/div[2]/div[2]/div[2]/form/div[2]/input').send_keys('1379%%%')
    waitForElement(driver, '//*[@id="login-dialog-dialog"]/div[2]/div[2]/div[2]/form/input[1]')
    driver.find_element_by_xpath('//*[@id="login-dialog-dialog"]/div[2]/div[2]/div[2]/form/input[1]').click()

    #Search Tag
    isFirst = False
    for index, curTag in enumerate(tags):
        pathNameCurTag = pathName + "#" + curTag;
        if not os.path.exists(pathNameCurTag):
            os.makedirs(pathNameCurTag)

        if(isFirst == False):
            isFirst = True
        else:
            waitForElement(driver, '//*[@id="search-query"]')
            for i in range(len(tags[index-1])+1):
                driver.find_element_by_xpath('//*[@id="search-query"]').send_keys(Keys.BACKSPACE)
            print("[Twitter]TagBackspace Complete")
            time.sleep(1)

        waitForElement(driver, '//*[@id="search-query"]')
        driver.find_element_by_xpath('//*[@id="search-query"]').send_keys("#" + curTag)
        time.sleep(1)
        waitForElement(driver, '//*[@id="search-query"]')
        driver.find_element_by_xpath('//*[@id="search-query"]').send_keys(Keys.RETURN)
        time.sleep(2)

        while len(driver.find_elements_by_class_name('tweet')) <= formatCount:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.2)

        # Save Text
        if (formatType[0] == 1):
            elements = []
            elements = driver.find_elements_by_class_name('tweet')
            del elements[formatCount:]

            f = codecs.open(pathNameCurTag + "/" + "#" + curTag + "(twitter)" + ".txt", "wb", "utf-8")
            for ele in elements:
                f.write(str(elements.index(ele) + 1) + " ")
                curText = None
                try:
                    curText = ele.find_element_by_class_name('js-tweet-text-container').text
                    f.write(curText + "\r\r\n\r\r\n")
                except:
                    print("[Twitter]No Text")

            f.close()

        # Save Image
        pathNameCurTagImg = pathNameCurTag + '/images';
        if not os.path.exists(pathNameCurTagImg):
            os.makedirs(pathNameCurTagImg)

        if (formatType[1] == 1):
            while len(driver.find_elements_by_class_name('AdaptiveMedia-photoContainer')) <= formatCount:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.2)

            elements = []
            elements = driver.find_elements_by_class_name('AdaptiveMedia-photoContainer')
            del elements[formatCount:]

            for ele in elements:
                try:
                    img_url = ele.get_attribute('data-image-url')
                    inputData = urlopen(img_url).read()

                    downloaded_image = "/" + "#" + curTag + str(elements.index(ele) + 1) + "(twitter)" + ".jpg"
                    sf = open(pathNameCurTagImg + downloaded_image, "wb")
                    sf.write(inputData)
                    sf.close()
                except:
                    print("[Twitter]Not Search Image Url")

        if (formatType[2] == 1):
            # text
            elements = []
            elements = driver.find_elements_by_class_name('tweet')
            del elements[formatCount:]

            dataList = []

            for ele in elements:
                # text
                curText = ele.find_element_by_class_name('js-tweet-text-container').text
                eleTagList = parsingTags(curText)

                # image
                isMultipleImage = False
                imgUrl = None
                multipleElementList = []
                imgUrlList = []
                try:
                    #imgUrl = ele.find_element_by_class_name('AdaptiveMedia').find_element_by_xpath(".//*//*//*").get_attribute('data-image-url')
                    #imgUrlList.append(imgUrl)
                    multipleElementList = ele.find_elements_by_class_name('AdaptiveMedia-photoContainer')
                    isMultipleImage = True
                except:
                    print("[Twitter]Null Image")

                if(isMultipleImage == True):
                    for multipleElement in multipleElementList:
                        imgUrlList.append(multipleElement.get_attribute('data-image-url'))

                eleData = {
                    "content": curText,
                    "image_url": imgUrlList,
                    "tags": eleTagList
                }
                dataList.append(eleData)

            targetData = {
                "keyword": curTag,
                "count": formatCount,
                "data": dataList
            }
            with open(pathNameCurTag+"/" +"#" + curTag + "(twitter)" + '.json', 'w') as f:
                json.dump(targetData, f)  # 저정된 데이터는 다른 python 에서 실행이된다.

        print("[Twitter] #" + curTag + " End")

typeSNS = {
    0 : runInstagram,
    1 : runFacebook,
    2 : runTwitter
}

@app.route('/_analysis_json', methods=['GET', 'OPTIONS', 'POST'])
@cross_origin()
def analysis_json():
    print("[analysis_json]")
    # data = json.dumps({})
    ###open local json file
    # if request.method == 'GET':
    #    with open('commands.json') as f:
    #        data = json.load(f)

    ###receive ajax json
    # else:
    # data = request.get_json(force=True)

    # TODO JSON 받아오기
    try:
        data = request.get_json(force=True)
        print(data)
        isSNS = data["isSNS"]
        curTaskId = data["taskId"]

        if(isSNS == 1): #SNS
            targetSNS = data["targetSNS"]
            tags = data["tags"]
            formatCount = data["format"]["count"]
            formatType = data["format"]["type"]

        else: #Custom
            curActions = data["actions"]
            curDate = data["scheduleDate"]    # 'scheduleDate' 부분추가
            curTaskIsSchedule = data["isSchedule"]
            curLoopCount = data["loopCount"]

    except:
        return jsonify(resultCode=1)


    # TODO JSON 저장
    with open('data'+str(curTaskId)+'.json', 'w') as f:
        json.dump(data, f) #저정된 데이터는 다른 python 에서 실행이된다.

    # TODO Thread 처리
    if (isSNS == 1):  #SNS
        for index, item in enumerate(targetSNS):
            if(item == 1):
                taskThread = Thread(target=typeSNS.get(index), args=[data])
                taskThreadList.append(taskThread)
                taskThread.start()

    else:   #Custom
        if (curTaskIsSchedule == str(1)):
            try:
                print("Schedule Run")
                parsedDate = dateutil.parser.parse(curDate) #파싱된 datetime obj
                scheduleTime = str(parsedDate.hour) + ":" + str(parsedDate.minute)
                schedule.every().day.at(scheduleTime).do(runTask,[data])
            except:
                print("schedule except")
                return jsonify(resultCode=0, taskId=curTaskId)

        else:
            print("Immediately Run")
            taskThread = Thread(name=curTaskId, target=runTask, args=[data])


            taskThreadList.append(taskThread)
            taskThread.start()




    # TODO 함수로
    # 이 부분에서 스케줄 등록하는 부분을 만들도록하자.
    # taskId
    #createSchtasks(curTaskId.parsedDate)

    # TODO 함수로 변경 파라미터 이것만있으면 됨?
    #runTaskThread(curTaskId,runTask,curActions,curTaskId.parsedDate) # 이 함수는 오직 쓰레드만 돌리면 된다.

    # TODO Delete Create json에 data가 추가가 되어야 한다.

    time.sleep(0.5)
    print("[End : analysis_json]")
    return jsonify(resultCode=1, taskId=curTaskId)

@app.route('/')
def index():
    return render_template('bar.html')

if __name__ == "__main__":
    app.run(debug=True)