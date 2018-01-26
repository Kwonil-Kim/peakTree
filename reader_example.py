#! /usr/bin/env python3
# coding=utf-8

import datetime
import matplotlib
matplotlib.use('Agg')
import numpy as np
import matplotlib.pyplot as plt

import sys, os
import peakTree
import peakTree.helpers as h
import peakTree.VIS_Colormaps as VIS_Colormaps

ts = h.dt_to_ts(datetime.datetime(2017,3,11,20,15))
rg = 3300
ts = 1489265220
#ts = 1489262407
rg = 3500

pTB = peakTree.peakTreeBuffer()
#pTB.load_peakTree_file('output/20170311_2000_peakTree.nc4')
# tree = pTB.get_tree_at(ts, rg)
#tree, _ = pTB.get_tree_at(ts, rg)
#print('tree is a dictionary of dictionaries')
#print(tree)
#print('pretty representation of the tree')
#print(peakTree.print_tree.travtree2text(tree))

pTB.load_peakTree_file('output/20170629_0930_peakTree_10s.nc4')


savepath = 'plots/'
if not os.path.isdir(savepath):
    os.makedirs(savepath)

dt_list = [h.ts_to_dt(ts) for ts in pTB.timestamps]
hrange = pTB.range
no_nodes = pTB.f.variables['no_nodes'][:]

plot_height_interval = [hrange[0], 10000]
plot_height_interval = [hrange[0], 3000]

fig, ax = plt.subplots(1, figsize=(10, 5.7))
pcmesh = ax.pcolormesh(matplotlib.dates.date2num(dt_list),
                       hrange,
                       np.transpose(no_nodes),
                       cmap='terrain_r', vmin=0, vmax=10)
cbar = fig.colorbar(pcmesh)
#ax.set_xlim([dt_list[0], dt_list[-1]])
#ax.set_ylim([height_list[0], height_list[-1]])
ax.set_xlim([dt_list[0], dt_list[-1]])
#ax.set_ylim([hrange[0], hrange[-1]])
ax.set_ylim(plot_height_interval)
ax.set_xlabel("Time UTC", fontweight='semibold', fontsize=15)
ax.set_ylabel("Height", fontweight='semibold', fontsize=15)
cbar.ax.set_ylabel("Number of nodes", fontweight='semibold', fontsize=15)
ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M'))

# ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(interval=3))
# ax.xaxis.set_minor_locator(matplotlib.dates.MinuteLocator(byminute=[0,30]))
# ax.yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(500))
ax.xaxis.set_major_locator(matplotlib.dates.MinuteLocator(byminute=[0,30]))
ax.xaxis.set_minor_locator(matplotlib.dates.MinuteLocator(byminute=range(0,61,5)))

ax.tick_params(axis='both', which='major', labelsize=14, 
               width=3, length=4)
ax.tick_params(axis='both', which='minor', width=2, length=3)
cbar.ax.tick_params(axis='both', which='major', labelsize=14,
                    width=2, length=4)

savename = 'plots' + "/" + dt_list[0].strftime("%Y%m%d_%H%M") + "_no_nodes.png"
fig.savefig(savename, dpi=250)



for i in range(3):
    Z_node = pTB.f.variables['Z'][:,:,i]

    fig, ax = plt.subplots(1, figsize=(10, 5.7))
    pcmesh = ax.pcolormesh(matplotlib.dates.date2num(dt_list),
                        hrange,
                        np.transpose(Z_node),
                        cmap='gist_rainbow', vmin=-40, vmax=10)
    cbar = fig.colorbar(pcmesh)
    #ax.set_xlim([dt_list[0], dt_list[-1]])
    #ax.set_ylim([height_list[0], height_list[-1]])
    ax.set_xlim([dt_list[0], dt_list[-1]])
    #ax.set_ylim([hrange[0], hrange[-1]])
    #ax.set_ylim([hrange[0], 10000])
    ax.set_ylim(plot_height_interval)
    ax.set_xlabel("Time UTC", fontweight='semibold', fontsize=15)
    ax.set_ylabel("Height", fontweight='semibold', fontsize=15)
    cbar.ax.set_ylabel("Reflectivity [dBZ]", fontweight='semibold', fontsize=15)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M'))

    # ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(interval=3))
    # ax.xaxis.set_minor_locator(matplotlib.dates.MinuteLocator(byminute=[0,30]))
    # ax.yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(500))
    ax.xaxis.set_major_locator(matplotlib.dates.MinuteLocator(byminute=[0,30]))
    ax.xaxis.set_minor_locator(matplotlib.dates.MinuteLocator(byminute=range(0,61,5)))

    ax.tick_params(axis='both', which='major', labelsize=14, 
                width=3, length=4)
    ax.tick_params(axis='both', which='minor', width=2, length=3)
    cbar.ax.tick_params(axis='both', which='major', labelsize=14,
                        width=2, length=4)

    savename = 'plots' + "/{}_reflectivity_node{}.png".format(dt_list[0].strftime("%Y%m%d_%H%M"), i)
    fig.savefig(savename, dpi=250)


    v_node = pTB.f.variables['v'][:,:,i]
    fig, ax = plt.subplots(1, figsize=(10, 5.7))
    pcmesh = ax.pcolormesh(matplotlib.dates.date2num(dt_list),
                        hrange,
                        np.transpose(v_node),
                        cmap=VIS_Colormaps.carbonne_map, vmin=-3, vmax=3)
    cbar = fig.colorbar(pcmesh)
    #ax.set_xlim([dt_list[0], dt_list[-1]])
    #ax.set_ylim([height_list[0], height_list[-1]])
    ax.set_xlim([dt_list[0], dt_list[-1]])
    #ax.set_ylim([hrange[0], hrange[-1]])
    #ax.set_ylim([hrange[0], 10000])
    ax.set_ylim(plot_height_interval)
    ax.set_xlabel("Time UTC", fontweight='semibold', fontsize=15)
    ax.set_ylabel("Height", fontweight='semibold', fontsize=15)
    cbar.ax.set_ylabel("Reflectivity [dBZ]", fontweight='semibold', fontsize=15)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M'))

    # ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(interval=3))
    # ax.xaxis.set_minor_locator(matplotlib.dates.MinuteLocator(byminute=[0,30]))
    # ax.yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(500))
    ax.xaxis.set_major_locator(matplotlib.dates.MinuteLocator(byminute=[0,30]))
    ax.xaxis.set_minor_locator(matplotlib.dates.MinuteLocator(byminute=range(0,61,5)))

    ax.tick_params(axis='both', which='major', labelsize=14, 
                width=3, length=4)
    ax.tick_params(axis='both', which='minor', width=2, length=3)
    cbar.ax.tick_params(axis='both', which='major', labelsize=14,
                        width=2, length=4)

    savename = 'plots' + "/{}_velocity_node{}.png".format(dt_list[0].strftime("%Y%m%d_%H%M"), i)
    fig.savefig(savename, dpi=250)

    ldrmax_node = pTB.f.variables['ldrmax'][:,:,i]
    fig, ax = plt.subplots(1, figsize=(10, 5.7))
    pcmesh = ax.pcolormesh(matplotlib.dates.date2num(dt_list),
                        hrange,
                        np.transpose(ldrmax_node),
                        cmap=VIS_Colormaps.ldr_map, vmin=-36, vmax=0)
    cbar = fig.colorbar(pcmesh)
    #ax.set_xlim([dt_list[0], dt_list[-1]])
    #ax.set_ylim([height_list[0], height_list[-1]])
    ax.set_xlim([dt_list[0], dt_list[-1]])
    #ax.set_ylim([hrange[0], hrange[-1]])
    #ax.set_ylim([hrange[0], 10000])
    ax.set_ylim(plot_height_interval)
    ax.set_xlabel("Time UTC", fontweight='semibold', fontsize=15)
    ax.set_ylabel("Height", fontweight='semibold', fontsize=15)
    cbar.ax.set_ylabel("Reflectivity [dBZ]", fontweight='semibold', fontsize=15)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M'))

    # ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(interval=3))
    # ax.xaxis.set_minor_locator(matplotlib.dates.MinuteLocator(byminute=[0,30]))
    # ax.yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(500))
    ax.xaxis.set_major_locator(matplotlib.dates.MinuteLocator(byminute=[0,30]))
    ax.xaxis.set_minor_locator(matplotlib.dates.MinuteLocator(byminute=range(0,61,5)))

    ax.tick_params(axis='both', which='major', labelsize=14, 
                width=3, length=4)
    ax.tick_params(axis='both', which='minor', width=2, length=3)
    cbar.ax.tick_params(axis='both', which='major', labelsize=14,
                        width=2, length=4)

    savename = 'plots' + "/{}_ldrmax_node{}.png".format(dt_list[0].strftime("%Y%m%d_%H%M"), i)
    fig.savefig(savename, dpi=250)