import psycopg2
import pandas as pd
import time
import uuid
import logging
import boto3
import io
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import NoAlertPresentException
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import requests
from japanera import Japanera, EraDate
from datetime import date, datetime
import re
import os
import traceback
import tabula
import urllib.parse
from dateutil.relativedelta import relativedelta
from base64 import b64decode
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

class Done(Exception):
	pass

class Parser:

	institute = "堺市" #sakai
	source_url = "https://www.city.sakai.lg.jp/sangyo/nyusatsu/kensetsu/system/nyusatsu/index.html"
	website_id = None
	main_index = 0

	possible_ins = []

	# real = False
	# bucket_path = 'tenders-crawler-test'
	# os.environ["DB_USERNAME"]="postgres"
	# os.environ["DB_PASSWORD"]=""
	# os.environ["DB_DEV"]="tenders-dev"
	# os.environ["DB_HOST"]="localhost"

	# connect to database
	connection = psycopg2.connect(
		host = os.environ['DB_HOST'],
		port = ,
		user = os.environ['DB_USERNAME'],
		password = os.environ['DB_PASSWORD'],
		database= os.environ['DB_DEV']
	   )
	cur = connection.cursor()

	def __init__ (self, web_chrome):
		self.driver = web_chrome

	def scrape_data(self):

		real = self.real
		source_url = self.source_url
		website_id = self.website_id
		institute = self.institute
		driver = self.driver

		# search institutions data
		if website_id:
			sql_twpi = "select institution_id, ci.institution_name, tu.id as target_id, prefercure_id, wd.website_id from core.institutions as ci inner join crawling.website_defaults as wd on ci.id = wd.institution_id inner join crawling.target_urls as tu on wd.website_id=tu.website_id where wd.website_id ="+str(website_id)
		else:
			sql_twpi = "select wd.institution_id, ci.institution_name, tu.id as target_id, wd.prefercure_id, wd.website_id from core.institutions as ci " + "inner join crawling.website_defaults as wd on ci.id = wd.institution_id inner join crawling.target_urls as tu on tu.website_id = wd.website_id " + "where institution_name ='"+institute+"' order by target_id asc"
					   
		get_tpwi = pd.read_sql(sql_twpi, con = self.connection)
		target_id, prefecture_id, website_id, institution_id = get_tpwi['target_id'].values[0], get_tpwi['prefercure_id'].values[0], get_tpwi['website_id'].values[0], get_tpwi['institution_id'].values[0]
		
		urls_pdf = None

		#categories needed to crawl
		category = ["//img[@src='index.images/button_ppi_koji.png']","//img[@src='index.images/button_ppi_buppin.png']"]
		
		for opt1 in range(1,3): #option 1 index
			for opt2 in range(2): #option 2 index

				for cat in category:

					driver.maximize_window()
					driver.get(source_url)
					
					#get data visible to system
					S = lambda X: driver.execute_script('return document.body.parentNode.scroll'+X)
					driver.set_window_size(1200,S('Height')) # May need manual adjustment

					driver.find_element_by_xpath(cat).click()
					time.sleep(3)

					#because clicking open to new windows
					driver.switch_to.window(driver.window_handles[-1])

					# website consist of many frame
					menu_frame = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "/html/frameset/frameset/frame[@name='menu_Frm']")))
					driver.switch_to.frame(menu_frame)

					# search button
					WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//a[text()='入札結果']"))).click()

					#frame changes again
					driver.switch_to.default_content()
					driver.switch_to.frame(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//frame[translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = 'mainfrm']"))))
					driver.switch_to.frame(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//frame[@name='cond']"))))

					WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//select[@name='Nendo']")))

					'''pages contains data'''
					# pages
					select = Select(driver.find_element_by_xpath("//select[@name='Nendo']"))
					select.select_by_index(opt1)

					# get latest page to get newest data
					select = Select(driver.find_element_by_xpath("//select[@name='ChoutatsuCD' or @name='BukyokuNOnyu']"))
					opts = len(select.options) - 1
					select.select_by_index(opts - opt2)

					# some js to load data
					driver.find_elements_by_xpath("//select[@name='ejMaxDisplayRowCount']/option")[-1].click()
					driver.execute_script("document.frm.submit();;return false")

					# frame changes again
					driver.switch_to.default_content()
					driver.switch_to.frame(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//frame[translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = 'mainfrm']"))))
					driver.switch_to.frame(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//frame[@name='list']"))))

					# loop the tables contain data
					tables = driver.find_elements_by_xpath("(//table[@class='borderTable group'])//tr")

					for row in range(300, len(tables)+1):
						
						# frame changes again
						driver.switch_to.default_content()
						driver.switch_to.frame(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//frame[translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = 'mainfrm']"))))
						driver.switch_to.frame(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//frame[@name='list']"))))

						# data extraction
						xpath = '//frame[@name="mainfrm"]'
						listing_id = 'NULL'
						subject = driver.find_element_by_xpath("(//table[@class='borderTable group'])//tr["+str(row)+"]//td[3]").text
						
						try:
							listing_id = subject.split('\n')[0]
							subject = subject.split('\n')[1]
						except Exception as e:
							pass

						announcement_date = driver.find_element_by_xpath("(//table[@class='borderTable group'])//tr["+str(row)+"]//td[2]").text
						
						try:
							announcement_date = announcement_date.split('\n')[0]
						except Exception as e:
							pass

						print(repr(subject), listing_id, repr(announcement_date))
						
						driver.find_element_by_xpath("(//table[@class='borderTable group'])//tr["+str(row)+"]//td[8]//a").click()
						web_element = driver.find_element_by_xpath('//html')	
						# web_element = driver.find_element_by_xpath('//html').screenshot_as_base64	

						time.sleep(3)
						announcement_date = self.get_date_from_text(announcement_date)
						announcement_date_raw, announcement_date_mod = self.modify_date(announcement_date)

						deadline_date = 'NULL'
						application_deadline_date_raw, application_deadline_date_mod = self.modify_date(deadline_date)

						url = driver.current_url
						driver.switch_to.default_content()
						driver.find_element_by_xpath(xpath).screenshot('ss/'+str(subject)+'.png')


						print(repr(announcement_date_mod), repr(subject), driver.current_url)

						item = {'institution' : institute,
								'target_id': target_id, 'prefecture_id': prefecture_id, 'website_id': website_id, 'institution_id': institution_id, 
								'website_id' : website_id, 
								'source_url': source_url,
								'listing_id': listing_id,
								'subject': subject,
								'announcement_date_raw': announcement_date_raw,
								'announcement_date_mod': announcement_date_mod,
								'application_deadline_date_mod': application_deadline_date_mod,
								'application_deadline_date_raw': application_deadline_date_raw,
								'publication_date_raw': 'NULL',
								'publication_date_mod': 'NULL',
								'listing_result_url': url,
								'bidding_method': 'NULL',
								'industry': 'NULL',
								'publication_date':'NULL',
								'screenshot_url': 'NULL',
								'details_url':'NULL'}   

						# if there is data save the data to db
						if (subject != 'NULL' and announcement_date != 'NULL'):
							self.process_item(item, driver, xpath)
						
						driver.switch_to.frame(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//frame[@name='BtnFrame']"))))

						driver.find_element_by_xpath("//span[@id='SP_L']").click()


		self.cur.close()
		self.connection.close()

		driver.quit()

		return 0

	def checkNumber(self, inputString):
		return any(char.isdigit() for char in inputString)

	def modify_date(self, date_table):
	
		chr_reiwa1 = b"\xe5\x85\x83".decode() # reiwa year first
		chr_day = b"\xe6\x97\xa5".decode() #日 tanda akhir tanggal
		chr_month = b"\xe6\x9c\x88".decode() #月 tanda akhir tanggal
		chr_year = b"\xe5\xb9\xb4".decode() #年 tanda akhir tanggal
		
		date_table = date_table.replace(chr_reiwa1,'01')
		# date_table = self.fullwidth_to_halfwidth(date_table)
		janera = Japanera()
		year = b"\xe5\xb9\xb4".decode()  # ?
		year_only = date_table.split('年')[0]
		
		if len(year_only) == 4 and year_only.isdigit():
			# ??02
			year = date_table.split('年')[0]
			now = date_table.split('年')[1]
			month = now.split('月')[0]
			now = now.split('月')[1]
			day = now.split('日')[0]
			date_bid = year+'-'+month+'-'+day
		elif len (year_only) == 4:
			japanese_format = b"\x25\x2d\x45\x25\x2d\x6f\xe5\xb9\xb4\x25\x6d\xe6\x9c\x88\x25\x64\xe6\x97\xa5".decode()  # %-E%-o?%m?%d?
			mod_date = janera.strptime(date_table, japanese_format)
			if(len(mod_date) == 0):
				return 'NULL','NULL'
			date_bid = mod_date[0].strftime("%Y-%m-%d")
		else:
			if self.checkNumber(year_only):
				# ??2 -> ??02
				japanese_format = b"\x25\x2d\x45\x25\x2d\x6f\xe5\xb9\xb4\x25\x6d\xe6\x9c\x88\x25\x64\xe6\x97\xa5".decode()  # %-E%-o?%m?%d?
				new_format = date_table[:2]+'0'+date_table[2:]
				date_table = ''
				for char in new_format:
					if self.checkNumber(char):
						date_table += str(int(char))
					else:
						date_table += char

				mod_date = janera.strptime(date_table, japanese_format)
				try:
					date_bid = mod_date[0].strftime("%Y-%m-%d")     
				except:
					return (date_table, 'NULL')
		
			else:
				# ???
				japanese_format = b"\x25\x2d\x45\x25\x2d\x6b\x4f\xe5\xb9\xb4\x25\x2d\x6b\x6d\xe6\x9c\x88\x25\x2d\x6b\x64\xe6\x97\xa5".decode()  # %-E%-kO?%-km?%-kd?
				# print(mod_date)
				try:
					date_bid = mod_date[0].strftime("%Y-%m-%d")     
				except:
					return (date_table, 'NULL')
		
		# print(date_bid)
		if(date_table == ''):
			date_table = 'NULL'
		
		if(date_bid == ''):
			date_bid = 'NULL'
		
		return (date_table, date_bid)

	def get_date_from_text(self, raw):

		modify_date = 'NULL'
		raw = raw.replace('元','1')
		raw = self.fullwidth_to_halfwidth(raw)
		if('日' in raw):
			raw = raw.split('日')[0]

		angka = re.findall("\d+",raw)


		if len(angka) == 3 :

			hari = int(angka[2])
			bulan = int(angka[1])
			tahun = int(angka[0])

			if hari>2000:
				temp = hari
				hari = tahun
				tahun = temp

			if bulan <= 12 and hari <=31:
				if tahun < 7: #jika lebih dari reiwa 8, krn tak akan ada reiwa 8
					modify_date = '令和'+angka[0]+'年'+angka[1]+'月'+angka[2]+'日'
				elif tahun > 2000:
					modify_date = angka[0]+'年'+angka[1]+'月'+angka[2]+'日'
				else:
					modify_date = '平成'+angka[0]+'年'+angka[1]+'月'+angka[2]+'日'
				modify_date = modify_date.replace('\r', '')

		if modify_date == 'NULL':
			found = re.findall('令和\d+年\d+月\d+日',raw)
			if len(found):
				modify_date = found[0]
			else:
				found = re.findall('平成\d+年\d+月\d+日',raw)
				if len(found):
					modify_date = found[0]
		return modify_date

	def fullwidth_to_halfwidth(self,s):

		FULLWIDTH_TO_HALFWIDTH = str.maketrans('１２３４５６７８９０','1234567890')

		return s.translate(FULLWIDTH_TO_HALFWIDTH).replace(' ','')
	""" SHOULD BE MODIFIED FOR EACH URL """
	def nullFillter(self, stra):
		# print(stra)
		if ('NULL' in stra) or (stra == '') or (stra == ' '):
			return 'NULL'
		elif("'" not in stra):
			return "'"+stra+"'"
		return stra
	
	""" SHOULD BE MODIFIED FOR EACH URL """
	def insert_listing_sql(self, website, target, screenshot_url, details_url, listing_id, listing_url, institution_raw, subject, bidding_method, industry,publication_date, application_deadline, announcement_date, time_now, institution_id, source_url, prefecture):
		#search industry_id dan bidding method.id
		industry_id , bidding_method_id = 'NULL','NULL'
		sql = "SELECT bidding_method_id FROM core.bidding_method_raw_texts WHERE raw_text = '"+bidding_method+"'"
		sql_bidding_method_id = pd.read_sql(sql, con = self.connection)
		
		if(len(sql_bidding_method_id)>0):
			bidding_method_id = sql_bidding_method_id['bidding_method_id'].values[0]

		sql = "SELECT industry_id FROM core.industry_raw_texts WHERE raw_text = '"+industry+"'"
		sql_industry_id = pd.read_sql(sql, con = self.connection)
		if(len(sql_industry_id)>0):
			industry_id = sql_industry_id['industry_id'].values[0]

		sql_listing_id = "SELECT id, website_id, target_id, publication_date, institution_id, prefecture_id FROM tender_data.listings WHERE " \
					 + "institution_id = "+ str(institution_id) +" and subject = '" + subject + "'and target_id = " + str(target) \
					 + " and website_id = " + str(website) + " and prefecture_id = " + str(prefecture) 
		get_val_check_listing = pd.read_sql(sql_listing_id, con = self.connection)
		
		# CREATE NEW LISTING
		sql_insert_new_listing = """INSERT INTO tender_data.listings(website_id, target_id, screenshot_url, details_url, manual_entry, hidden,
								 removed_from_website, manually_inspected, listing_id, listing_url, institution_raw, subject, area_raw, bidding_method_raw, industry_raw, requirements, publication_date, application_deadline, winner_publication_date, created_at, modified_at, last_queried_at, institution_id, area_id, bidding_method_id, industry_id, source_url, display_url, published_date, prefecture_id) VALUES
								 ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}) """ \
								 .format(self.nullFillter(str(website)), self.nullFillter(str(target)), self.nullFillter(str(screenshot_url)), self.nullFillter(str(details_url)), False, False, False, False, self.nullFillter(str(listing_id)), self.nullFillter(str(listing_url)), self.nullFillter(str(institution_raw)), self.nullFillter(str(subject)), 'NULL',self.nullFillter(str(bidding_method)), self.nullFillter(str(industry)), 'NULL', self.nullFillter(str(publication_date)), self.nullFillter(str(application_deadline)), self.nullFillter(str(announcement_date)), self.nullFillter(str(time_now)), 'NULL', self.nullFillter(str(time_now)), self.nullFillter(str(institution_id)), \
								 'NULL', self.nullFillter(str(bidding_method_id)), self.nullFillter(str(industry_id)), self.nullFillter(str(source_url)), 'NULL', 'NULL', self.nullFillter(str(prefecture)))
		
		if len(get_val_check_listing) == 0:
			self.cur.execute(sql_insert_new_listing)
			self.connection.commit()
		else:
			print('pass double listing_id')
		
	def process_item(self, item, driver, xpath):
		institute = item['institution']
		source_url = item['source_url']

		# GET TARGET ID, WEBSITE ID, PREFECTURE ID, INSTITUTION ID
		website = item['website_id']
		target, prefecture, website, institution_id = item['target_id'], item['prefecture_id'], item['website_id'], item['institution_id']

		 #INITIALIZE SOME VARIABLE
		id_pdf = uuid.uuid4()
		id_screenshot = uuid.uuid4()
		now = datetime.now()
		
		detail_url =  item['details_url']
		screenshot_url =  'https://'+self.bucket_path+'.s3-ap-northeast-1.amazonaws.com/png/'+str(institution_id)+'/'+str(id_screenshot)+'.png'

		



		# IS THERE A SAME LISTING
		if(item['application_deadline_date_mod'] != 'NULL' and item['application_deadline_date_mod'] != '' ):
			listing_id = "SELECT id, website_id, target_id, publication_date, institution_id, prefecture_id FROM tender_data.listings WHERE " \
					 + "institution_id = "+ str(institution_id) +" and subject = '" + item['subject'] + "'and target_id = " + str(target) \
					 + " and website_id = " + str(website) + " and prefecture_id = " + str(prefecture) + " and application_deadline = '" + str(item['application_deadline_date_mod']) + "'"
		else:
			listing_id = "SELECT id, website_id, target_id, publication_date, institution_id, prefecture_id FROM tender_data.listings WHERE " \
					 + "institution_id = "+ str(institution_id) +" and subject = '" + item['subject'] + "'and target_id = " + str(target) \
					 + " and website_id = " + str(website) + " and prefecture_id = " + str(prefecture)
		
		get_val_check_listing = pd.read_sql(listing_id, con = self.connection)
		
		# CHECK WHETHER LISTING ID IS EXIST OR NOT, IF YES CHANGE TO NULL
		if item['listing_id'] != 'NULL':
			select_listing_id = "select * from tender_data.listings where listing_id = "+self.nullFillter(item['listing_id'])
			get_check_listing_id = pd.read_sql(select_listing_id, con = self.connection)
			if len(get_check_listing_id) != 0:
				item['listing_id'] = 'NULL'
		
		## INSERT TO LISTINGS
		if len(get_val_check_listing) == 0: #jika listing belum ada

			self.insert_listing_sql(website=website, target=target, 
				screenshot_url=screenshot_url, 
				details_url=detail_url, listing_id=item['listing_id'], listing_url=item['listing_result_url'], 
				institution_raw = institute, subject = item['subject'], bidding_method = item['bidding_method'], 
				industry = item['industry'], publication_date = item['publication_date_mod'] ,
				application_deadline = item['application_deadline_date_mod'], 
				announcement_date = item['announcement_date_mod'], 
				time_now = str(now), institution_id = institution_id , 
				source_url = source_url, prefecture = prefecture)

			print("Add to DB: {}".format(item['subject']))
		else:
			try:
				double_check_result = "select * from tender_data.listings_result where subject = '" + item['subject'] + "' and listing_result_url = '" + item['listing_result_url'] + "' and source_url = '" + source_url + "'"
				get_double_check = pd.read_sql(double_check_result, con = self.connection)
				if len(get_double_check) != 0:
					print("Pass: {}".format(item['subject']))
				else:
					self.insert_listing_sql(website=website, target=target, screenshot_url=screenshot_url, details_url=detail_url, listing_id=item['listing_id'], listing_url=item['listing_result_url'], institution_raw = institute, subject = item['subject'], bidding_method = item['bidding_method'], industry = item['industry'],  publication_date = item['publication_date_mod'], application_deadline = item['application_deadline_date_mod'], announcement_date = item['announcement_date_mod'], time_now = str(now), institution_id = institution_id , source_url = source_url, prefecture = prefecture)
					print("Add similar data to DB: {} {}".format(item['subject'], '=================='))
			except Exception as e:
				print(e)
		
		get_listing_id = pd.read_sql(listing_id, con = self.connection)

		# CHECK DATA IN LISTING_RESULT
		for list_id_db in range (len(get_listing_id)):
			sql_check_previous_data = "SELECT * FROM tender_data.listings_result WHERE subject = '"+ item['subject'] + "' AND listing_id = " + str(get_listing_id['id'].values[list_id_db]) + " AND listing_result_url = '" + item['listing_result_url'] + "'"
			get_previous_data = pd.read_sql(sql_check_previous_data, con = self.connection)
			
			try:
				if len(get_previous_data) == 0:

					img64 = driver.find_element_by_xpath(xpath).screenshot_as_base64	

					image = io.BytesIO(b64decode(img64))
					if self.real == True:
						s3_resource = boto3.resource('s3', aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID'], aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY'])
						object = s3_resource.Object(self.bucket_path, 'png/'+str(institution_id)+'/'+str(id_screenshot)+'.png')
						object.put(Body=image)
					else:
						driver.find_element_by_xpath(xpath).screenshot('ss/'+str(id_screenshot)+'.png')
				
					# INSERT TO POSTGRES LISTING_RESULT                     
					
					sql_insert_result = """INSERT INTO tender_data.listings_result(listing_id, manual_entry, manually_inspected, subject,       
										subject_raw, announcement_date,announcement_date_raw, listing_result_url, source_url, screenshot_url, details_url, created_by, created_at, modified_by, modified_at)
										VALUES ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})""" \
										.format(get_listing_id['id'].values[list_id_db], False, False, "'"+item['subject']+"'", "'"+item['subject']+ "'",  "'"+item['announcement_date_mod']+"'", "'"+item['announcement_date_raw']+"'", 
										"'"+item['listing_result_url']+"'", "'"+source_url+"'", "'"+screenshot_url+"'", "'"+detail_url+"'", 'NULL', "'"+str(now)+"'", 'NULL', "'"+str(now)+"'")
			
					self.cur.execute(sql_insert_result)
					self.connection.commit()
					self.main_index +=1
					print(self.main_index, end=' ')
					
					print("Data inserted in listing_result {} {}".format(get_listing_id['id'].values[list_id_db], '\n'))
					
				else:
					
					print("Duplicate data in listing_result {} {}".format(get_listing_id['id'].values[list_id_db], '\n'))
					
				break
			
			except Exception as e:
				print("Check data with same subject on listing_id {} {}".format(get_listing_id['id'].values[list_id_db], '\n'))
				self.cur.execute("ROLLBACK")

	def pdf_read(self, pdf_url):
		chr_listing_id, chr_subject, chr_day, chr_month, chr_year = b"\xe5\x8f\xb7".decode(), b"\xe5\x90\x8d".decode(), b"\xe6\x97\xa5".decode(),b"\xe6\x9c\x88".decode(),b"\xe5\xb9\xb4".decode()

		listings, subjects, deadlines, announcements, publications = [],[],[],[],[]
		listing_id, subject = 'NULL', 'NULL'
		deadline_date, announcement_date, publication_date  = 'NULL','NULL','NULL'

		ketemu_listing_id = False
		ketemu_announcement = False
		ketemu_subject = False
		page = 0

		table_data = []
		table_data_line = []
		raw_announcements, raw_subjects = [],[]
		

		# GET SUBJECT, URL FOR EACH PDF
		# DOWNLOAD PDF AND EXTRACT THE DATE
		pdf_content = requests.get(pdf_url)
		listing_id, subject, announcement_date = 'NULL','NULL','NULL'

		print(pdf_url)

		try:
			''' table data box '''
			pdf_website_buffer = io.BytesIO(pdf_content.content)
			table_data = tabula.read_pdf(pdf_website_buffer, pages='all', silent=True, lattice=True)
		except:
			print('notable')

		if len(table_data) == 0:
			''' table data baris perbaris '''
			pdf_website_buffer = io.BytesIO(pdf_content.content)
			table_data_line = tabula.read_pdf(pdf_website_buffer, output_format='json',stream=True, guess=False, silent=True, pages='all')

		# ### harus di baca per line ### #
			
		# table_data = []
		# print(len(table_data))
		for page in range(len(table_data)):
			
			listing_id = 'NULL'
			announcement_date, publication_date, deadline_date = 'NULL', 'NULL', 'NULL'

			ketemu_listing_id, ketemu_subject, ketemu_deadline, ketemu_publication, ketemu_announcement = False, False, False, False, False
			
			table = table_data[page].values.tolist()
			table.insert(0, list(table_data[page].columns))
			# print(table[0])
			# for row in range(len(table)):
			# 	line = table[row]
			# 	# print(line)
			# 	col = 0
			# 	if line[col] == line[col]:
			# 		print(line)
					# break
			subject = table[0][1]
			announcement_date = table[1][1]
			# table = []
				
			print(page,repr(listing_id), repr(subject), repr(announcement_date))

			announcements.append(announcement_date)
			deadlines.append(deadline_date)
			subjects.append(subject)
			listings.append(listing_id)
			publications.append(publication_date)

		return listings, subjects, deadlines, announcements, publications

	def manual_url (self):
		urls = []
		return urls


chrome_options = webdriver.ChromeOptions()
# chrome_options.add_argument('--headless')
chrome_options.add_argument("start-maximized")
chrome_options.add_argument("enable-automation")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-infobars")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-browser-side-navigation")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-features=VizDisplayCompositor")
driver_web = webdriver.Chrome(chrome_options=chrome_options)
driver_web.set_window_size(1920, 1080)
driver_web.set_script_timeout(120)
driver_web.set_page_load_timeout(120)

scrape = Parser(driver_web)
scrape.scrape_data()
