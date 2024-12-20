#!/usr/bin/env python3
"""
Non-neural baseline system for the SIGMORPHON 2020 Shared Task 0.
Author: Mans Hulden
Modified by: Tiago Pimentel
Modified by: Jordan Kodner
Modified by: Omer Goldman
Last Update: 22/03/2021
"""

import sys, os, getopt
from functools import wraps

def hamming(s,t):
    """
    This function calculates the hamming distance between two strings.

    Args:
        s   string 1
        t   string 2

    Return:  
        value of hamming distance
    """
    return sum(1 for x,y in zip(s,t) if x != y)


def halign(s,t):
    """
    Align two strings by Hamming distance.
    
    Args:
        s   string 1
        t   string 2
    
    Return: 
        aligned version of the strings 
    """
    slen = len(s)
    tlen = len(t)
    minscore = slen + tlen + 1

    for upad in range(0, tlen+1):
        upper = '_' * upad + s + (tlen - upad) * '_'
        lower = slen * '_' + t
        score = hamming(upper, lower)
        if score < minscore:
            bu = upper
            bl = lower
            minscore = score

    for lpad in range(0, slen+1):
        upper = tlen * '_' + s
        lower = (slen - lpad) * '_' + t + '_' * lpad
        score = hamming(upper, lower)
        if score < minscore:
            bu = upper
            bl = lower
            minscore = score

    zipped = list(zip(bu,bl))
    newin  = ''.join(i for i,o in zipped if i != '_' or o != '_')
    newout = ''.join(o for i,o in zipped if i != '_' or o != '_')
    return newin, newout


def levenshtein(s, t, inscost = 1.0, delcost = 1.0, substcost = 1.0):
    """
    Recursive implementation of Levenshtein, with alignments returned.
    """
    @memolrec
    def lrec(spast, tpast, srem, trem, cost):
        if len(srem) == 0:
            return spast + len(trem) * '_', tpast + trem, '', '', cost + len(trem)
        if len(trem) == 0:
            return spast + srem, tpast + len(srem) * '_', '', '', cost + len(srem)

        addcost = 0
        if srem[0] != trem[0]:
            addcost = substcost

        return min((lrec(spast + srem[0], tpast + trem[0], srem[1:], trem[1:], cost + addcost),
                   lrec(spast + '_', tpast + trem[0], srem, trem[1:], cost + inscost),
                   lrec(spast + srem[0], tpast + '_', srem[1:], trem, cost + delcost)),
                   key = lambda x: x[4])

    answer = lrec('', '', s, t, 0)
    return answer[0],answer[1],answer[4]


def memolrec(func):
    """
    Memoizer for Levenshtein.
    """
    cache = {}
    @wraps(func)
    def wrap(sp, tp, sr, tr, cost):
        if (sr,tr) not in cache:
            res = func(sp, tp, sr, tr, cost)
            cache[(sr,tr)] = (res[0][len(sp):], res[1][len(tp):], res[4] - cost)
        return sp + cache[(sr,tr)][0], tp + cache[(sr,tr)][1], '', '', cost + cache[(sr,tr)][2]
    return wrap


def alignprs(lemma, form):
    """
    Break lemma/form into three parts:
    IN:  1 | 2 | 3
    OUT: 4 | 5 | 6
    1/4 are assumed to be prefixes, 2/5 the stem, and 3/6 a suffix.
    1/4 and 3/6 may be empty.

    Args:
        lemma   input string
        form    output string

    Return:
        prefixes, roots, and suffixes of lemma and form respectively
    """

    al = levenshtein(lemma, form, substcost = 1.1) # Force preference of 0:x or x:0 by 1.1 cost
    alemma, aform = al[0], al[1]
    # leading spaces
    lspace = max(len(alemma) - len(alemma.lstrip('_')), len(aform) - len(aform.lstrip('_')))
    # trailing spaces
    tspace = max(len(alemma[::-1]) - len(alemma[::-1].lstrip('_')), len(aform[::-1]) - len(aform[::-1].lstrip('_')))
    return alemma[0:lspace], alemma[lspace:len(alemma)-tspace], alemma[len(alemma)-tspace:], aform[0:lspace], aform[lspace:len(alemma)-tspace], aform[len(alemma)-tspace:]


def prefix_suffix_rules_get(lemma, form):
    """
    Extract a number of suffix-change and prefix-change rules based on a given example lemma+inflected form.
    
    Args:
        lemma   input string
        form    output string
    
    Return:
        prefix rules and suffix rules generated based on the arguments
    """
    lp, lr, ls, fp, fr, fs = alignprs(lemma, form)  # Get six parts: three for input, three for output

    def generate_rules(ins, outs): # Consolidate the logic for generating rules (iterating, slicing, removing underscores)
        """
        Generate rules based on input and output strings.
        Removes underscores in the process.
        """
        rules = set()
        for i in range(min(len(ins), len(outs))):
            rules.add((ins[i:], outs[i:]))
        return {(x[0].replace('_', ''), x[1].replace('_', '')) for x in rules}

    # Generate suffix rules
    srules = generate_rules(lr + ls + ">", fr + fs + ">")

    # Generate prefix rules (if applicable)
    prules = set()
    if len(lp) >= 0 or len(fp) >= 0:
        inp = "<" + lp
        outp = "<" + fp
        prules = generate_rules(inp, outp)

    return prules, srules

def apply_best_rule(lemma, msd, allprules, allsrules):
    """
    Applies the longest-matching suffix-changing rule given an input form and the MSD. 
    Length ties in suffix rules are broken by frequency. 
    For prefix-changing rules, only the most frequent rule is chosen.
    
    Args:
        lemma       word to be transformed
        msd         morphological description of the lemma
        allprules   set of prefix rules
        allsrules   set of suffix rules
    
    Return:
        inflected version of the lemma
    """

    bestrulelen = 0
    base = "<" + lemma + ">"
    if msd not in allprules and msd not in allsrules:
        return lemma # Haven't seen this inflection, so bail out

    if msd in allsrules:
        applicablerules = [(x[0],x[1],y) for x,y in allsrules[msd].items() if x[0] in base]
        if applicablerules:
            bestrule = max(applicablerules, key = lambda x: (len(x[0]), x[2], len(x[1])))
            base = base.replace(bestrule[0], bestrule[1])

    if msd in allprules:
        applicablerules = [(x[0],x[1],y) for x,y in allprules[msd].items() if x[0] in base]
        if applicablerules:
            bestrule = max(applicablerules, key = lambda x: (x[2]))
            base = base.replace(bestrule[0], bestrule[1])

    base = base.replace('<', '')
    base = base.replace('>', '')
    return base


def numleadingsyms(s, symbol):
    """
    The function counts the leading symbol in a string

    Args:
        s       string
        symbol  specific symbol to be counted

    Return:
        number of symbols
    """
    return len(s) - len(s.lstrip(symbol))


def numtrailingsyms(s, symbol):
    """
    The function counts the trailing symbol in a string
    
    Args:
        s       string
        symbol  specific symbol to be counted

    Return:
        number of symbols
    """
    return len(s) - len(s.rstrip(symbol))

###############################################################################

def main(argv):
    options, remainder = getopt.gnu_getopt(argv[1:], 'ohp:', ['output','help','path='])
    TEST, OUTPUT, HELP, path = False,False, False, 'data/'
    for opt, arg in options:
        # output prediction results
        if opt in ('-o', '--output'):
            OUTPUT = True
        # run on test data
        if opt in ('-t', '--test'):
            TEST = True
        # call for the help document
        if opt in ('-h', '--help'):
            HELP = True
        # specify the file path of data
        if opt in ('-p', '--path'):
            path = arg

    if HELP:
            print("\n*** Baseline for the SIGMORPHON 2020 shared task ***\n")
            print("By default, the program runs all languages only evaluating accuracy.")
            print("To create output files, use -o")
            print("The training and dev-data are assumed to live in ./part1/development_languages/")
            print("Options:")
            print(" -o         create output files with guesses (and don't just evaluate)")
            print(" -t         evaluate on test instead of dev")
            print(" -p [path]  data files path. Default is ../data/")
            quit()

    # reading the file to access data
    totalavg, numlang = 0.0, 0
    for lang in [os.path.splitext(d)[0] for d in os.listdir(path) if '.trn' in d]:
        allprules, allsrules = {}, {}
        if not os.path.isfile(path + lang +  ".trn"):
            continue
        lines = [line.strip() for line in open(path + lang + ".trn", "r", encoding='utf8') if line != '\n']

        # First, test if language is predominantly suffixing or prefixing
        # If prefixing, work with reversed strings
        prefbias, suffbias = 0,0
        for l in lines:
            lemma, _, form = l.split(u'\t')
            aligned = halign(lemma, form)
            if ' ' not in aligned[0] and ' ' not in aligned[1] and '-' not in aligned[0] and '-' not in aligned[1]:
                prefbias += numleadingsyms(aligned[0],'_') + numleadingsyms(aligned[1],'_')
                suffbias += numtrailingsyms(aligned[0],'_') + numtrailingsyms(aligned[1],'_')
        for l in lines: # Read in lines and extract transformation rules from pairs
            lemma, msd, form = l.split(u'\t')
            if prefbias > suffbias:
                lemma = lemma[::-1]
                form = form[::-1]
            prules, srules = prefix_suffix_rules_get(lemma, form)

            for rules, storage in [(prules, allprules), (srules, allsrules)]: # consolidating the msd creation codes using a loop
                if msd not in storage and len(rules) > 0:
                    storage[msd] = {}

            for rules, storage in [(prules, allprules), (srules, allsrules)]: # consolidating the rule-counting codes
                for r in rules:
                    if (r[0], r[1]) in storage[msd]:
                        storage[msd][(r[0], r[1])] += 1
                    else:
                        storage[msd][(r[0], r[1])] = 1


        # Run eval on dev
        devlines = [line.strip() for line in open(path + lang + ".dev", "r", encoding='utf8') if line != '\n']
        if TEST:
            devlines = [line.strip() for line in open(path + lang + ".tst", "r", encoding='utf8') if line != '\n']
        numcorrect = 0
        numguesses = 0
        if OUTPUT:
            outfile = open(path + lang + ".out", "w", encoding='utf8')
        # apply best rules on the lemma based on msd
        for l in devlines:
            lemma, msd, correct = l.split(u'\t')
            if prefbias > suffbias: # consolidate the prefix-biased condition
                lemma = lemma[::-1]  # Reverse lemma for prefix alignment
                outform = apply_best_rule(lemma, msd, allprules, allsrules)[::-1]  # Reverse the result
                lemma = lemma[::-1]  # Restore original lemma
            else:
                outform = apply_best_rule(lemma, msd, allprules, allsrules)

            if outform == correct:
                numcorrect += 1
            numguesses += 1
            if OUTPUT:
                outfile.write(lemma + "\t" + msd + "\t" + outform + "\n")

        if OUTPUT:
            outfile.close()

        # calculate the accuracy of prediction
        numlang += 1
        totalavg += numcorrect/float(numguesses)

        print(lang + ": " + str(str(numcorrect/float(numguesses)))[0:7])

    print("Average accuracy", totalavg/float(numlang))


if __name__ == "__main__":
    main(sys.argv)
