#! /usr/bin/env python3
# coding=utf-8

import datetime
#import matplotlib
#matplotlib.use('Agg')
#import numpy as np
#import matplotlib.pyplot as plt

#import sys, os
import peakTree
import peakTree.helpers as h

pTB = peakTree.peakTreeBuffer()
#pTB.load_spec_file('data/D20170311_T2000_2100_Lim_zspc2nc_v1_02_standard.nc4')
pTB.load_spec_file('data/D20170311_T2000_2100_Lim_zspc2nc_v1_02_standard_faster.nc4')

#pTB.load_spec_file('data/D20170605_T0030_0045_Pol_zspc2nc_v1_02_standard.nc4')
pTB.load_spec_file('data/D20170629_T0930_0945_Pol_zspc2nc_v1_02_standard.nc4')
pTB.assemble_time_height('output/')

