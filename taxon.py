from wikidataintegrator import wdi_core, wdi_login
import copy
import bs4
import requests
import json
import local
from datetime import datetime
import bibtexparser
from IPython.display import Image, HTML

class external_data(object):
    def __init__(self, inaturalist_id):
        self.now = datetime.now()
        self.inaturalist_id=inaturalist_id
        self.inaturalist_data = self.fetch_inaturalist(inaturalist_id)
        self.inaturalist_parent_data = self.fetch_inaturalist(self.inaturalist_data[0]["parent_id"])
        self.wikidata = self.fetch_wikidata()
        self.qid = self.wikidata["main_rank"]["taxon"].replace({'http://www.wikidata.org/entity/': ''}, regex=True)
        self.parent_inat_qid = self.wikidata["parent_rank"]["parent_taxon"].replace({'http://www.wikidata.org/entity/': ''}, regex=True)
        self.gbif_id = self.wikidata["main_rank"]["gBifTaxonId"].loc[0]
        self.gbif_data = self.fetch_gbif(self.gbif_id)
        self.gbif_parent_data = self.fetch_gbif(self.gbif_data["parentKey"])
        self.bhl_references = self.fetch_bhl().entries
        if self.gbif_data["parent"] == self.inaturalist_parent_data[0]["name"]:
            self.parent_gbif_qid = self.parent_inat_qid
        else:
            parent_query = """
                                    SELECT ?parent_taxon ?taxonname ?inatTaxonId ?gBifTaxonId ?commons  WHERE {
                                      ?parent_taxon wdt:P31 wd:Q16521 ; 
                                             wdt:P225 '"""
            parent_query += self.inaturalist_parent_data[0]["name"]
            parent_query += "', ?taxonname .}"
            gbif_parent_result = wdi_core.WDFunctionsEngine.execute_sparql_query(parent_query, as_dataframe=True)
            self.parent_gbif_qid = gbif_parent_result["parent_taxon"].replace({'http://www.wikidata.org/entity/': ''}, regex=True)
        if "commons" in self.wikidata["main_rank"].columns:
            self.commons = self.wikidata["main_rank"]["commons"]

    def fetch_inaturalist(self, id):
        url = "https://www.inaturalist.org/taxa/"+str(id)
        html = requests.get(url).text
        soup = bs4.BeautifulSoup(html, features="html.parser")
        for cd in soup.findAll(text=True):
            if  "CDATA" in cd:
                datatext = cd.split("\"results\":")
                if len(datatext) > 1:
                    return eval(datatext[1].split("}.results")[0].replace("false", "False").replace("true", "True").replace("null", "None"))

    @staticmethod
    def fetch_gbif(id):
        gbifapi = "https://api.gbif.org/v1/species/" + str(id)
        return json.loads(requests.get(gbifapi).text)

    def fetch_wikidata(self):
        query = """
                SELECT ?taxon ?taxonname ?inatTaxonId ?gBifTaxonId ?commons  WHERE {
                  ?taxon wdt:P31 wd:Q16521 ; 
                         wdt:P225 '"""
        query += self.inaturalist_data[0]["name"]
        query += """', ?taxonname .
                  OPTIONAL {?taxon wdt:P3151 '"""
        query += str(self.inaturalist_data[0]["id"])
        query += """', ?inatTaxonId .} 
                OPTIONAL {  ?commons schema:about ?taxon ;
                                    schema:isPartOf <https://commons.wikimedia.org/> .}
                OPTIONAL {?taxon wdt:P846 ?gBifTaxonId .}}
                """
        parent_query = """
                        SELECT ?parent_taxon ?taxonname ?inatTaxonId ?gBifTaxonId ?commons  WHERE {
                          ?parent_taxon wdt:P31 wd:Q16521 ; 
                                 wdt:P225 '"""
        parent_query += self.inaturalist_parent_data[0]["name"]
        parent_query += """', ?taxonname .
                          OPTIONAL {?taxon wdt:P3151 '"""
        parent_query += str(self.inaturalist_parent_data[0]["id"])
        parent_query += """', ?inatTaxonId .} 
                        OPTIONAL {  ?commons schema:about ?parent_taxon ;
                                            schema:isPartOf <https://commons.wikimedia.org/> .}
                        OPTIONAL {?parent_taxon wdt:P846 ?gBifTaxonId .}}
                        """
        results = dict()
        results["main_rank"] = wdi_core.WDFunctionsEngine.execute_sparql_query(query, as_dataframe=True)
        results["parent_rank"] = wdi_core.WDFunctionsEngine.execute_sparql_query(parent_query, as_dataframe=True)
        return results

    def update_wikidata(self):
        taxonQids = dict()
        taxonQids["species"] = "Q7432"
        taxonQids["SPECIES"] = "Q7432"
        taxonQids["genus"] = "Q34740"
        taxonQids["GENUS"] = "Q34740"

        ## References
        stated_in = [wdi_core.WDItemID("Q16958215", prop_nr="P248", is_reference=True)]
        statements = []

        stated_in_inat_id = [
            wdi_core.WDItemID("Q16958215", prop_nr="P248", is_reference=True),
            wdi_core.WDExternalID(str(self.inaturalist_id), prop_nr="P3151", is_reference=True)
        ]

        stated_in_gbif_id = [
            wdi_core.WDItemID("Q1531570", prop_nr="P248", is_reference=True),
            wdi_core.WDExternalID(str(self.gbif_id), prop_nr="P846", is_reference=True)
        ]

        # iNaturualist taxon rank
        if self.inaturalist_data[0]["rank"] == "species":
            statements.append(
                wdi_core.WDItemID(value=taxonQids[self.inaturalist_data[0]["rank"]], prop_nr="P105", references=[copy.deepcopy(stated_in_inat_id)])
            )
        # GBIF taxon rank
        if self.gbif_data["rank"] == "SPECIES":
            statements.append(
                wdi_core.WDItemID(value=taxonQids["species"], prop_nr="P105",
                                  references=[copy.deepcopy(stated_in_gbif_id)])
            )

        # parent taxon
        if self.parent_inat_qid.loc[0] != "":
            statements.append(
                wdi_core.WDItemID(value=self.parent_inat_qid.loc[0], prop_nr="P171",
                                  references=[copy.deepcopy(stated_in_inat_id)])
            )
        if self.parent_gbif_qid.loc[0] != "":
            statements.append(
                wdi_core.WDItemID(value=self.parent_gbif_qid.loc[0], prop_nr="P171",
                                  references=[copy.deepcopy(stated_in_gbif_id)])
            )

        #iNaturalist identifier
        statements.append(
            wdi_core.WDExternalID(str(self.inaturalist_data[0]["id"]), prop_nr="P3151", references=[copy.deepcopy(stated_in)]))
        item = wdi_core.WDItemEngine(
            wd_item_id=str(self.wikidata["main_rank"].loc[0]["taxon"]).replace("http://www.wikidata.org/entity/", ""), data=statements)
        # return item.get_wd_json_representation()
        return item.write(self.login)

    def fetch_bhl(self):
        bhlbibtexurl = "https://www.biodiversitylibrary.org/namelistdownload/?type=b&name=" + self.inaturalist_data[0][
            "name"].replace(" ", "_")
        bibtex = requests.get(bhlbibtexurl).text
        return bibtexparser.loads(bibtex)

    def create_wikipedia_stub(self, infobox_image):
        inaturalist = self.inaturalist_data[0]
        inaturalist_parent = self.inaturalist_parent_data[0]
        inaturalist_qid = self.qid.loc[0]
        gbifdata = self.gbif_data

        if 'preferred_common_name' in inaturalist.keys():
            exordium = "'''''{0}''''', also known by its common name '''{1}'''".format(inaturalist["name"], inaturalist[
                'preferred_common_name'])
        else:
            exordium = "'''''{0}'''''".format(inaturalist["name"])

        ## recommended reading
        if len(self.bhl_references)>0:
            recommend_reading = """== Sources ==
        {{refbegin | 33em}}"""
            for source in self.bhl_references:
                if source["ENTRYTYPE"]=="book":
                    if "pages" in source.keys():
                        pages = source["pages"]
                    else: pages = ""
                    if "volume" in source.keys():
                        volume = source["volume"]
                    else: volume = ""

                    recommend_reading += """\n* {{{{cite book|url={url} 
|publisher={publisher}
|page={page}
|year={year}
|title={title}
|volume={volume}}}}}""".format(url=source["url"], publisher=source["publisher"],page=pages,year=source["year"], title=source["title"], volume=volume)
            recommend_reading += "\n{{refend}}"
                                                       




        en_wikipedia_article = """{{{{Speciesbox 
| image = {0}
| parent = {1}
| taxon = {2}
| authority = {9}
}}}}

{8} is a [[{3}]] from the [[{4}]] [[{1}]] <ref name="inaturalist-{2}">{{{{cite web |title={2} |url=https://www.inaturalist.org/taxa/{5}-{6} |website=iNaturalist |access-date={10} |language=en}}}}</ref>. 

==References==
{{{{Reflist}}}}
{recommended_reading}


{{{{Commons}}}}
{{{{Taxonbar|from={7}}}}}
{{{{stub}}}}""".format(infobox_image, inaturalist_parent["name"], inaturalist["name"], inaturalist["rank"],
                   inaturalist_parent["rank"], inaturalist["id"], inaturalist["name"].replace(" ", "-"),
                   inaturalist_qid, exordium, gbifdata["authorship"], self.now.strftime("%Y-%m-%d"), recommended_reading=recommend_reading)

        return en_wikipedia_article






