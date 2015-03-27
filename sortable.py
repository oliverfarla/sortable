"""
This program is a solution to sortable.com's programming challenge of matching products with product descriptions.
It was written to run in python3 and took about 5 minutes to run.
The general approach is to parse the product descriptions in varying ways and producing a list of tokens (strings),
then checking if these lists of tokens match the ones in the product description. 
Penalties are given for parsing methods which are partially destructive, as well as out of order matchings and a
few other imperfect matchings. If the total score from penalties is high enough, the product is matched.

My philosopy behind the way the program is written was to prioritize experimentation over performance since a
heuristic solution is likely the best, which usually requires testing. This was accomplished by writing a simple 
architecture which tests various interpretations of the product & listing text (called "parsings" in the program) and
looks for potential matches. That way it was easy to view the results and add new parsings for situations that were
initially overlooked. The architecture was written to allow overriding pentalties and comparison algorithms along
the way to facilitate different types of comparisons.

"""
import sys
import json
import re
import copy

MIN_SCORE = -2.0 #minimum score to allow a matching

assert(len(sys.argv)==4)
products_file = sys.argv[1]
listings_file = sys.argv[2]
results_file = sys.argv[3]
#products_file = "products.txt" #sys.argv[1]
#listings_file = "listings.txt" #sys.argv[2]
#results_file = "results.txt" #sys.argv[3]
products = []
with open(products_file) as f:
    products = [json.loads(line) for line in f]
    #keys: product_name, manufacturer, model, family, announced-date
with open(listings_file) as f:
    listings = [json.loads(line) for line in f]
    #keys: title, manufacturer, currency, price

#Helper functions for parsing strings and finding subsets of lists

def ReplaceDashes(s,s2=""):
    return s.replace("-",s2)

def SplitCamelCase(s):
    s2 = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', s)
    return re.sub('([a-z0-9])([A-Z])', r'\1 \2', s2)

def ReplaceNonAlphaNumeric(s,replaceWith=''):
    sx= re.sub('[^a-zA-Z0-9_\s]+', replaceWith, s)
    return sx

def SplitOnSpaces(s):
    return " ".join(s.lower().split()).split()

#if the model number is something like GV-999X, drop the X, but don't drop the X in GV-999XX
#this pattern seems common for cases when X is a colour. 
def DropLastLetterOnModelNumber(lst):
    return [s[0:-1] if re.search('\d\[a-z]$',s) else s for s in lst ]

#options used for IsSubsetOf and IsSublistOf
class MatchOptions:
    """
    A set of options for how lists of strings are compared.
    Used in functions like IsSubsetOf and IsSublistOf
    """
    def __init__(self,allowPrefix=False,requireContiguousSublist=False):
        self.AllowPrefix=allowPrefix
        self.requireContiguousSublist=requireContiguousSublist

#returns matched indices or None
def IsSubsetOf(sublist,searchlist,matchOptions=None):
    """
    Returns the indices where the sublist first matched the searchlist.
    Returns None if not sublist is not a subset of searchlist.
    """
    if matchOptions==None:
        matchOptions=MatchOptions()
    sortedIndices = sorted(range(len(searchlist)), key=lambda x:searchlist[x])
    sortedSublist = sorted(sublist)
    i=0
    j=0
    indices = []
    def IndexMatch():
        if matchOptions.AllowPrefix:
            return searchlist[sortedIndices[j]].startswith(sortedSublist[i])
        else:
            return sortedSublist[i]==searchlist[sortedIndices[j]]
    while i<len(sublist) and j<len(searchlist):
        if IndexMatch():
            indices.append(sortedIndices[j])
            i+=1 # no j+=1 incase duplicate i
        elif sortedSublist[i]<searchlist[sortedIndices[j]]:
            i+=1
        else:
            j+=1
    if len(indices) < len(sublist):
        return None
    return indices

#returns match indices, or None
def IsSublistOf(sublist,searchlist,matchOptions=None):
    """
    Returns the indices where the sublist first matched the searchlist in order.
    Returns None if not possible.
    """
    if matchOptions==None:
        matchOptions=MatchOptions()
    i=0
    j=0
    matchIndices=[]
    def IndexMatch():
        if matchOptions.AllowPrefix:
            return searchlist[j].startswith(sublist[i])
        else:
            return searchlist[j]==sublist[i]
    while(i<len(sublist)):
        oldi=i
        while j < len(searchlist):
            if IndexMatch():
                matchIndices.append(j)
                i+=1
                break
            j+=1
        if i==oldi:
            return None
    if len(matchIndices) < len(sublist):
        return None
    return matchIndices
    


class Parsing:
    """
    An abstract class that represents a way of parsing a text line (title/manufacturer/etc...)
    parseAction: a of string->list(string) that tokenizes a text string into words
    usagePenalty: an automatic numeric penalty for using this parsing 
    """
    def __init__ (self,parseAction, usagePenalty):
        self.parseAction = parseAction
        self.usagePenalty = usagePenalty
    
    def Match(self,matchType,listingLine,productLine,matchOptions=None):
        return NotImplemented #concrete classes should return a numeric score

class BasicParsing(Parsing):
    """
    A basic implementation of Parsing with a few features.
    tooFarInString: causes a penalty if the matched word "eg Kodak" is found too far to the right in the text line.
    tooFarInStringIndexPenalty: the penalty incurred by tooFarInString
    allowPrefixForModel: allows the model number to only match as a prefix
    allowPrefixForModelPenalty: the penalty incurred by allowPrefixForModel
    subsetMatchPenalty: the penalty for matching the subset instead of sublist
    """
    def __init__ (self,parseAction, usagePenalty, tooFarInStringIndex=10,tooFarInStringIndexPenalty=-0.5,
                  allowPrefixForModel=False,allowPrefixForModelPenalty=-0.5,subsetMatchPenalty=-0.5):
        Parsing.__init__(self, parseAction, usagePenalty)
        self.tooFarInStringIndex = tooFarInStringIndex
        self.tooFarInStringIndexPenalty = tooFarInStringIndexPenalty
        self.allowPrefixForModel = allowPrefixForModel
        self.allowPrefixForModelPenalty = allowPrefixForModelPenalty
        self.subsetMatchPenalty=subsetMatchPenalty
    
    def runMatch(self,matchFunction,matchType,listingLine,productLine,matchOptions=None):
        if matchOptions == None:
            matchOptions = MatchOptions()
        score = 0
        indices = matchFunction(productLine.words,listingLine.words,matchOptions)
        if indices == None:
            if self.allowPrefixForModel and matchType=="model":
                tempOptions = copy.copy(matchOptions)
                tempOptions.AllowPrefix=True
                indices = matchFunction(productLine.words,listingLine.words,tempOptions)
                if indices != None:
                    score +=self.allowPrefixForModelPenalty
        if indices == None:
            return None
        if max(indices) > self.tooFarInStringIndex+len(productLine.words):
            score += self.tooFarInStringIndexPenalty
        return score
    
    def Match(self,matchType,listingLine,productLine,matchOptions=None):
        score = self.runMatch(IsSublistOf,matchType,listingLine,productLine,matchOptions)
        if score == None:
            #try subset match instead
            score = self.runMatch(IsSubsetOf,matchType,listingLine,productLine,matchOptions)
            if score ==None:
                return None
            score +=self.subsetMatchPenalty
        score += self.usagePenalty
        return score

class ParsedLine:
    """
    The result of Parsing a text line with a Parsing.
    words: List of strings
    parsing: Parsing object
    """
    def __init__(self, words, parsing):
        self.words = words
        self.parsing = parsing

class Listing:
    """
    Represents a product listing
    """
    
    def __init__(self,item,parsings):
        self.item = item
        self.parsings = parsings
        self.titles = {parsing:ParsedLine(parsing.parseAction(item["title"]),parsing) for parsing in parsings}
        self.manufacturers = {parsing:ParsedLine(parsing.parseAction(item["manufacturer"]),parsing) for parsing in parsings}
        self.matchings = {} #key: product, value: score
        self.manufacturerScores = {}
        self.familiesScores = {}
        self.modelsScores = {}
    
    def GetBestMatches(self,minScore=None):
        bestScore = None
        scores = [score for score in listing.matchings.values() if score != None]
        if len(scores)>0:
            bestScore = max(scores)
        if minScore!=None or bestScore>minScore:
            bestProducts = [k for k in listing.matchings.keys() if listing.matchings[k] == bestScore]
            return bestProducts
        else:
            return []

class Product:
    """
    Represents a product
    """
    allManufacturers = {}
    allFamilies = {}
    allModels = {}
    def __init__(self,item,parsings):
        self.item = item
        self.parsings = parsings
        if item["manufacturer"] not in Product.allManufacturers:
            Product.allManufacturers[item["manufacturer"]] = {parsing:ParsedLine(parsing.parseAction(item["manufacturer"]),parsing) for parsing in parsings}
        if "family" in item and item["family"] not in Product.allManufacturers:
            Product.allFamilies[item["family"]] = {parsing:ParsedLine(parsing.parseAction(item["family"]),parsing) for parsing in parsings}
        if item["model"] not in Product.allManufacturers:
            Product.allModels[item["model"]] = {parsing:ParsedLine(parsing.parseAction(item["model"]),parsing) for parsing in parsings}
        self.matches = []


#create parsings:
allParsings = []
allParsings.append(BasicParsing(lambda s: SplitOnSpaces(s.lower()),0))
allParsings.append(BasicParsing(lambda s: SplitOnSpaces(SplitCamelCase(s)),0))
allParsings.append(BasicParsing(lambda s: SplitOnSpaces(SplitCamelCase(ReplaceDashes(s,""))),0))
allParsings.append(BasicParsing(lambda s: DropLastLetterOnModelNumber(SplitOnSpaces(SplitCamelCase(ReplaceDashes(s," ")))),-0.5))
allParsings.append(BasicParsing(lambda s: SplitOnSpaces(ReplaceNonAlphaNumeric(s)),-0.5))
allParsings.append(BasicParsing(lambda s: DropLastLetterOnModelNumber(SplitOnSpaces(ReplaceNonAlphaNumeric(SplitCamelCase(ReplaceDashes(s))," "))),-1.5))

#build listings & products from imported JSON
listings = [Listing(listing,allParsings) for listing in listings]
products = [Product(product,allParsings) for product in products]

#stores already computed scores using tuples as the keys (only exists for performance reasons)
scoresCache = {}

#returns None or a numeric score
def CalcBestScore(matchType,listingLineDict, productLineDict,matchOptions=None):
    bestScore = None
    #tup = (matchType,listingLineDict,productLineDict,matchOptions)
    #if tup in scoreCache:
    #    return scoreCache[tup]
    for parsing in allParsings:
        if not parsing in listingLineDict or not parsing in productLineDict:
            continue
        listingLine = listingLineDict[parsing]
        productLine = productLineDict[parsing]
        score = parsing.Match(matchType,listingLine,productLine,matchOptions)
        if score !=None:
            bestScore = score if bestScore == None else max(score,bestScore)
    #scoreCache[tup] = bestScore
    return bestScore

#Calculate best score for manufacturer
def DoManufacturer(listing,product,matchOptions=None):
    manu_score = None
    if "manufacturer" in product.item:
        manu = product.item["manufacturer"]
        if "manufacturer" in listing.item:
            tup = ("manufacturer-manufacturer", product.item["manufacturer"],listing.item["manufacturer"],matchOptions)
            if tup in scoresCache:
                return scoresCache[tup]
            manu_score = CalcBestScore("manufacturer", listing.manufacturers,Product.allManufacturers[manu],matchOptions)
            scoresCache[tup] = manu_score
        else:
            tup = ("manufacturer-title", product.item["manufacturer"],listing.item["title"],matchOptions)
            if tup in scoresCache:
                return scoresCache[tup]
            manu_score = CalcBestScore("manufacturer", listing.titles,Product.allManufacturers[manu],matchOptions)
            scoresCache[tup] = manu_score
        listing.manufacturerScores[manu] = manu_score
    return manu_score

#Calculate best score for family
def DoFamily(listing, product, matchOptions=None):
    fam_score = None
    if "family" in product.item:
        fam = product.item["family"]
        tup = ("family-title", product.item["family"],listing.item["title"],matchOptions)
        if tup in scoresCache:
            return scoresCache[tup]
        fam_score = CalcBestScore("family",listing.titles,Product.allFamilies[fam],matchOptions)
        if fam_score == None:
            fam_score = -1.0 #family name not found in title
        scoresCache[tup] = fam_score
    else:
        fam_score = -0.5 #product with no family could be strange give that product a penalty
    return fam_score

#Calculate best score for model
def DoModel(listing,product,matchOptions=None):
    mod_score = None
    if "model" in product.item:
        mod = product.item["model"]
        tup = ("model-title", product.item["model"],listing.item["title"],matchOptions)
        if tup in scoresCache:
            return scoresCache[tup]
        if mod in listing.modelsScores:
            return listing.modelsScores[mod]
        mod_score = CalcBestScore("model",listing.titles,Product.allModels[mod],matchOptions)
        if mod_score !=None:
            mod_score+= len(mod)/1000.0 #give an advantage to the longest matching model #
        scoresCache[tup] = mod_score
    return  mod_score

missed = []
#look for matches matches:
for listing in listings:
    for product in products:
        manu_score= DoManufacturer(listing,product)
        if manu_score ==None:
            listing.matchings[product]=None
            continue
        fam_score= DoFamily(listing,product)
        if fam_score ==None:
            listing.matchings[product]=None
            continue
        mod_score= DoModel(listing,product)
        if mod_score ==None:
            listing.matchings[product]=None
            continue
        listing.matchings[product] = manu_score + fam_score + mod_score
    bestProducts = listing.GetBestMatches(MIN_SCORE)
    if len(bestProducts)==1:
        bestProducts[0].matches.append(listing)
        #print("Match "+products[0].item["product_name"]+"  -  "+listing.item["title"]+"\n")
    else:
        #print(len(bestProducts))
        missed.append(listing)
        #print(listing.item)

totalMatches = 0
#output results
with open("results.txt","w") as f:
    for product in products:
        result = {"product_name": product.item["product_name"], 
                  "listings": [listing.item for listing in product.matches]}
        totalMatches += len(product.matches)
        f.write(json.dumps(result)+"\n")
#print(totalMatches)

