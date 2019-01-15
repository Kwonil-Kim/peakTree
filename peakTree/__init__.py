#! /usr/bin/env python3
# coding=utf-8
""""""
"""
Author: radenz@tropos.de
"""

import matplotlib
matplotlib.use('Agg')

import datetime
import logging
import ast
import subprocess
import netCDF4
import numpy as np
import matplotlib.pyplot as plt
from . import helpers as h
from . import print_tree
import toml

log = logging.getLogger(__name__)
# log.setLevel(logging.DEBUG)
# stream_handler = logging.StreamHandler()
# stream_handler.setLevel(logging.INFO)
# formatter = logging.Formatter('%(levelname)s: %(message)s')
# stream_handler.setFormatter(formatter)
# file_handler = logging.FileHandler(filename='../test.log', mode='w')
# formatter = logging.Formatter('%(asctime)s-%(name)s-%(levelname)s-%(message)s', datefmt='%H:%M:%S')
# file_handler.setFormatter(formatter)
# file_handler.setLevel(logging.DEBUG)
# log.addHandler(file_handler)
# log.addHandler(stream_handler)

#@profile
def detect_peak_simple(array, lthres):
    """detect noise separated peaks

    Args:
        array: with Doppler spectrum
        lthres: threshold
    Returns:
        list of indices (as tuple)
    """
    ind = np.where(array > lthres)[0].tolist()
    jumps = [ind.index(x) for x, y in zip(ind, ind[1:]) if y - x != 1]
    runs = np.split(ind, [i+1 for i in jumps])
    if runs[0].shape[0] > 0:
        peakindices = [(elem[0], elem[-1]) for elem in runs]
    else:
        peakindices = []
    return peakindices


#@profile
def get_minima(array):
    """get the minima of an array by calculating the derivative

    Returns:
        list of ``(index, value at index)``
    """
    #sdiff = np.ma.diff(np.sign(np.ma.diff(array)))
    sdiff = np.diff(np.sign(np.diff(array)))
    rising_1 = (sdiff == 2)
    rising_2 = (sdiff[:-1] == 1) & (sdiff[1:] == 1)
    rising_all = rising_1
    rising_all[1:] = rising_all[1:] | rising_2
    min_ind = np.where(rising_all)[0] + 1
    minima = list(zip(min_ind, array[min_ind]))
    return sorted(minima, key=lambda x: x[1])


def split_peak_ind_by_space(peak_ind):
    """split a list of peak indices by their maximum space
    use for noise floor separated peaks
    
    Args:
        peak_ind: list of peak indices ``[(163, 165), (191, 210), (222, 229), (248, 256)]``
    Returns:
        left sublist, right sublist
    """
    if len(peak_ind) == 1:
        return [peak_ind, peak_ind]
    left_i = np.array([elem[0] for elem in peak_ind])
    right_i = np.array([elem[1] for elem in peak_ind])
    spacing = left_i[1:]-right_i[:-1]
    split_i = np.argmax(spacing)
    return peak_ind[:split_i+1], peak_ind[split_i+1:]


def peak_pairs_to_call(peak_ind):
    """generator that yields the tree structure of a peak list based on spacing
    
    Args:
        peak_ind: list of peak indices
    Yields:
        tree structure for noise separated peaks (includes recursive ``yield from`` for children)
    """
    left, right = split_peak_ind_by_space(peak_ind)
    if left != right:
        yield (left[0][0], left[-1][-1]), (right[0][0], right[-1][-1])
        yield from peak_pairs_to_call(left)
        yield from peak_pairs_to_call(right)


class Node():
    """class to generate the tree
    
    Args:
        bounds: boundaries in bin coordinates
        spec_chunk: spectral reflectivity within this node
        noise_thres: noise threshold hat separated this peak
        root: flag indicating if root node
        parent_lvl: level of the parent node
    """
    def __init__(self, bounds, spec_chunk, noise_thres, root=False, parent_lvl=0):
        self.bounds = bounds
        self.children = []
        self.level = 0 if root else parent_lvl + 1
        self.root = root
        self.threshold = noise_thres
        self.spec = spec_chunk
        self.prom_filter = 1.
        # TODO prominence filter to 2dB (Shupe 2004) or even 6 (Williams 2018)
        #print('at node ', bounds, h.lin2z(noise_thres), spec_chunk)

    def add_noise_sep(self, bounds_left, bounds_right, thres):
        """add a nose separated peak/node
        
        Args:
            bounds_left: boundaries of the left peak
            bounds_right: boundaries of the right peak
            thres: threshold that separates the peaks
        """
        fitting_child = list(filter(lambda x: x.bounds[0] <= bounds_left[0] and x.bounds[1] >= bounds_right[1], self.children))
        if len(fitting_child) == 1:
            #recurse on
            fitting_child[0].add_noise_sep(bounds_left, bounds_right, thres)
        else:
            # insert here
            spec_left = self.spec[bounds_left[0]-self.bounds[0]:bounds_left[1]+1-self.bounds[0]]
            spec_right = self.spec[bounds_right[0]-self.bounds[0]:bounds_right[1]+1-self.bounds[0]]
            prom_left = spec_left[spec_left.argmax()]/thres
            prom_right = spec_right[spec_right.argmax()]/thres
            if h.lin2z(prom_left) > self.prom_filter and h.lin2z(prom_right) > self.prom_filter:
                self.children.append(Node(bounds_left, spec_left, thres, parent_lvl=self.level))
                self.children.append(Node(bounds_right, spec_right, thres, parent_lvl=self.level))
            else:
                #print('omitted noise sep. peak at ', bounds_left, bounds_right, h.lin2z(prom_left), h.lin2z(prom_right))
                pass

    def add_min(self, new_index, current_thres, ignore_prom=False):
        """add a local minimum

        Args:
            new_index: bin index of minimum
            current_threshold: reflectivity that separates the peaks
            ignore_prom (optional): ignore the prominence threshold
        """
        if new_index < self.bounds[0] or new_index > self.bounds[1]:
            raise ValueError("child out of parents bounds")
        fitting_child = list(filter(lambda x: x.bounds[0] <= new_index and x.bounds[1] >= new_index, self.children))
        if len(fitting_child) == 1:
            fitting_child[0].add_min(new_index, current_thres)
        # or insert here
        else:
            spec_left = self.spec[:new_index+1-self.bounds[0]]
            prom_left = spec_left[spec_left.argmax()]/current_thres
            # print('spec_chunk left ', self.bounds[0], new_index, h.lin2z(prom_left), spec_left)
            spec_right = self.spec[new_index-self.bounds[0]:]
            prom_right = spec_right[spec_right.argmax()]/current_thres
            # print('spec_chunk right ', new_index, self.bounds[1], h.lin2z(prom_right), spec_right)

            cond_prom = [h.lin2z(prom_left) > self.prom_filter, h.lin2z(prom_right) > self.prom_filter]
            if all(cond_prom) or ignore_prom:
                self.children.append(Node((self.bounds[0], new_index), 
                                     spec_left, current_thres, parent_lvl=self.level))
                self.children.append(Node((new_index, self.bounds[1]), 
                                     spec_right, current_thres, parent_lvl=self.level))
            else:
                #print('omitted peak at ', new_index, 'between ', self.bounds, h.lin2z(prom_left), h.lin2z(prom_right))
                pass 

    def __str__(self):
        string = str(self.level) + ' ' + self.level*'  ' + str(self.bounds) + "   [{:4.3e}]".format(self.threshold)
        return "{}\n{}".format(string, ''.join([t.__str__() for t in self.children]))


#@profile
def traverse(Node, coords):
    """traverse a node and recursively all subnodes
    
    Args:
        Node (:class:`Node`): Node object to traverse
        coords: Nodes coordinate as list
    Yields:
        all child nodes recursively"
    """
    yield {'coords': coords, 'bounds': Node.bounds, 'thres': Node.threshold}
    for i, n in enumerate(Node.children):
        yield from traverse(n, coords + [i])


def full_tree_id(coord):
    '''convert a coordinate to the id from the full binary tree

    Args:
        coord: Nodes coordinate as a list
    Returns:
        index as in full binary tree
    Example:

        .. code-block:: python

            [0] -> 0
            [0, 1] -> 2
            [0, 0, 0] -> 3
            [0, 1, 1, 0] -> 13
    '''
    idx = 2**(len(coord)-1)-1
    for ind, flag in enumerate(reversed(coord)):
        if flag == 1:
            idx += (2**ind)
    #print(coord,'->',idx)
    return idx


#@profile
def coords_to_id(traversed):
    """calculate the id in level-order from the coordinates

    Args:
        input: traversed tree as list of dict
    Returns:
        traversed tree (dict) with id as key
    """
    traversed_id = {}  
    #print('coords to id, traversed ', traversed) 
    for node in traversed:
        k = full_tree_id(node['coords'])
        traversed_id[k] = node
        parent = [k for k, val in traversed_id.items() if val['coords'] == node['coords'][:-1]]
        traversed_id[k]['parent_id'] = parent[0] if len(parent) == 1 else -1
    # level_no = 0
    # while True:
    #     current_level =list(filter(lambda d: len(d['coords']) == level_no+1, traversed))
    #     if len(current_level) == 0:
    #         break
    #     for d in sorted(current_level, key=lambda d: sum(d['coords'])):
    #         k = full_tree_id(d['coords'])
    #         traversed_id[k] = d
    #         parent = [k for k, val in traversed_id.items() if val['coords'] == d['coords'][:-1]]
    #         traversed_id[k]['parent_id'] = parent[0] if len(parent) == 1 else -1
    #     level_no += 1
    #print('coords to id, traversed_id ', traversed_id)
    return traversed_id


def moment(x, Z):
    """mean, rms, skew for a vel, Z part of the spectrum
    
    Args:
        x: velocity of bin
        Z: spectral reflectivity
    Returns:
        dict with v, width, skew
    """
    mean = np.sum(x*Z)/np.sum(Z)
    rms = np.sqrt(np.sum(((x-mean)**2)*Z)/np.sum(Z))
    skew = np.sum(((x-mean)**3)*Z)/(np.sum(Z)*(rms**3))
    return {'v': mean, 'width': rms, 'skew': skew}


#@profile
def calc_moments(spectrum, bounds, thres):
    """calc the moments following the formulas given by Görsdorf2015 and Maahn2017

    Args:
        spectrum: spectrum dict
        bounds: boundaries (bin no)
        thres: threshold used
    Returns
        moment, spectrum
    """
    Z = np.sum(spectrum['specZ'][bounds[0]:bounds[1]+1])
    # TODO add the masked pocessing for the moments
    #spec_masked = np.ma.masked_less(spectrum['specZ'], thres, copy=True)
    masked_Z = h.fill_with(spectrum['specZ'], spectrum['specZ_mask'], 0.0)
    masked_Z = h.fill_with(masked_Z, (masked_Z<thres), 0.0)
    moments = moment(spectrum['vel'][bounds[0]:bounds[1]+1], masked_Z[bounds[0]:bounds[1]+1])
    
    #spectrum['specZco'] = spectrum['specZ']/(1+spectrum['specLDR'])
    #spectrum['specZcx'] = (spectrum['specLDR']*spectrum['specZ'])/(1+spectrum['specLDR'])

    ind_max = spectrum['specSNRco'][bounds[0]:bounds[1]+1].argmax()

    prominence = spectrum['specZ'][bounds[0]:bounds[1]+1][ind_max]/thres
    prominence_mask = spectrum['specZ_mask'][bounds[0]:bounds[1]+1][ind_max]
    moments['prominence'] = prominence if not prominence_mask else 1e-99
    #assert np.all(validSNRco.mask == validSNRcx.mask)
    #print('SNRco', h.lin2z(spectrum['validSNRco'][bounds[0]:bounds[1]+1]))
    #print('SNRcx', h.lin2z(spectrum['validSNRcx'][bounds[0]:bounds[1]+1]))
    #print('LDR', h.lin2z(spectrum['validSNRcx'][bounds[0]:bounds[1]+1]/spectrum['validSNRco'][bounds[0]:bounds[1]+1]))
    moments['z'] = Z
    
    # new try for the peak ldr (sum, then relative; not spectrum of relative with sum)
    if not np.all(spectrum['specZ_mask']) and not np.all(spectrum['specZcx_mask']):
        min_Zco = np.min(spectrum["specZ"][~spectrum['specZ_mask']])
        min_Zcx = np.min(spectrum["specZcx"][~spectrum['specZcx_mask']])
        Zco = spectrum['specZ']
        Zcx = spectrum['specZcx']
        #ldr = np.nansum(masked_Zcx[bounds[0]:bounds[1]+1]/min_Zco)/np.sum(masked_Zco[bounds[0]:bounds[1]+1]/min_Zcx)
        ldr = np.nansum(Zcx[bounds[0]:bounds[1]+1])/np.sum(Zco[bounds[0]:bounds[1]+1])
        ldrmax = spectrum["specLDR"][bounds[0]:bounds[1]+1][ind_max]
    else:
        ldr = np.nan
        ldrmax = np.nan
    
    # ldr calculation after the debugging session
    ldrmax = spectrum["specLDR"][bounds[0]:bounds[1]+1][ind_max]
    if not np.all(spectrum['specZcx_mask']):
        ldr2 = np.sum(spectrum['specZcx_validcx'][bounds[0]:bounds[1]+1])/np.sum(spectrum['specZ_validcx'][bounds[0]:bounds[1]+1])
    else:
        ldr2 = np.nan

    decoup = 10**(spectrum['decoupling']/10.)
    #print('ldr ', h.lin2z(ldr), ' ldrmax ', h.lin2z(ldrmax), 'new ldr ', h.lin2z(ldr2))
    #print('ldr without decoup', h.lin2z(ldr-decoup), ' ldrmax ', h.lin2z(ldrmax-decoup), 'new ldr ', h.lin2z(ldr2-decoup))

    # for i in range(spectrum['specZcx_validcx'].shape[0]):
    #     print(i, h.lin2z(np.array([spectrum['specZ'][i], spectrum['specZcx_validcx'][i], spectrum['specZ_validcx'][i]])), spectrum['specZcx_mask'][i])

    moments['ldr'] = ldr
    moments['ldr'] = ldr2 if (np.isfinite(ldr2) and not np.allclose(ldr2, 0.0)) else np.nan
    #moments['ldr'] = ldr2-decoup
    moments['ldrmax'] = ldrmax

    #moments['minv'] = spectrum['vel'][bounds[0]]
    #moments['maxv'] = spectrum['vel'][bounds[1]]

    return moments, spectrum



def calc_moments_wo_LDR(spectrum, bounds, thres):
    """calc the moments following the formulas given by Görsdorf2015 and Maahn2017

    Args:
        spectrum: spectrum dict
        bounds: boundaries (bin no)
        thres: threshold used
    Returns
        moment, spectrum
    """
    Z = np.sum(spectrum['specZ'][bounds[0]:bounds[1]+1])
    masked_Z = h.fill_with(spectrum['specZ'], spectrum['specZ_mask'], 0.0)
    masked_Z = h.fill_with(masked_Z, (masked_Z<thres), 0.0)
    moments = moment(spectrum['vel'][bounds[0]:bounds[1]+1], masked_Z[bounds[0]:bounds[1]+1])
    
    ind_max = spectrum['specSNRco'][bounds[0]:bounds[1]+1].argmax()

    prominence = spectrum['specZ'][bounds[0]:bounds[1]+1][ind_max]/thres
    prominence_mask = spectrum['specZ_mask'][bounds[0]:bounds[1]+1][ind_max]
    moments['prominence'] = prominence if not prominence_mask else 1e-99
    moments['z'] = Z
    moments['ldr'] = 0.0
    moments['ldr'] = 0.0
    moments['ldrmax'] = 0.0
    return moments, spectrum



def tree_from_spectrum(spectrum):
    """generate the tree and return a traversed version

    .. code-block:: python

        spectrum = {'ts': self.timestamps[it], 'range': self.range[ir], 'vel': self.velocity,
            'specZ': specZ, 'noise_thres': specZ.min()}

    Args:
        spectrum (dict): spectra dict
    Returns:
        traversed tree
    """

    # for i in range(spectrum['specZ'].shape[0]):
    #     if not spectrum['specZ'][i] == 0:
    #         print(i, spectrum['vel'][i], h.lin2z(spectrum['specZ'][i]))
    masked_Z = h.fill_with(spectrum['specZ'], spectrum['specZ_mask'], 0)
    peak_ind = detect_peak_simple(masked_Z, spectrum['noise_thres'])
    # filter all peaks with that are only 1 bin wide
    peak_ind = list(filter(lambda e: e[1]-e[0] > 0, peak_ind))
    if peak_ind:
        # print('peak ind at noise  level', peak_ind)
        if len(peak_ind) == 0:
            t = Node(peak_ind[0], spectrum['specZ'][peak_ind[0]:peak_ind[1]+1], spectrum['noise_thres'], root=True)
        else:
            t = Node((peak_ind[0][0], peak_ind[-1][-1]), spectrum['specZ'][peak_ind[0][0]:peak_ind[-1][-1]+1], spectrum['noise_thres'], root=True)
            for peak_pair in peak_pairs_to_call(peak_ind):
                # print('peak pair', peak_pair)
                t.add_noise_sep(peak_pair[0], peak_pair[1], spectrum['noise_thres'])

        # minima only inside main peaks
        #minima = get_minima(np.ma.masked_less(spectrum['specZ'], spectrum['noise_thres']*1.1))
        #minima = get_minima(np.ma.masked_less(masked_Z, spectrum['noise_thres']*1.1))
        minima = get_minima(h.fill_with(masked_Z, masked_Z<spectrum['noise_thres']*1.1, 1e-30))
        for m in minima:
            # print('minimum ', m)
            if m[1]>spectrum['noise_thres']*1.1:
                t.add_min(m[0], m[1])
            else:
                #print('detected minima too low', m[1], spectrum['noise_thres']*1.1)
                pass
        #print(t)
        traversed = coords_to_id(list(traverse(t, [0])))
        for i in traversed.keys():
            #if i == 0:
            #    moments, spectrum =  calc_moments(spectrum, traversed[i]['bounds'], traversed[i]['thres'])
            #else:
            if 'specZcx' in spectrum:
                moments, _ = calc_moments(spectrum, traversed[i]['bounds'], traversed[i]['thres'])
            else:
                moments, _ = calc_moments_wo_LDR(spectrum, traversed[i]['bounds'], traversed[i]['thres'])
            traversed[i].update(moments)
            #print('traversed tree')
            #print(i, traversed[i])
        #print(print_tree.travtree2text(traversed))

        #new skewness split
        chop = False
        if chop:
            nodes_with_min = list(traversed.keys())
            all_parents = [n['parent_id'] for n in traversed.values()]
            leafs = set(traversed.keys()) - set(all_parents)
            nodes_to_split = [k for k,v in traversed.items() if k in leafs and np.abs(v['skew']) > 0.4]
            print('all_parents ', all_parents, 'leafs ', leafs, ' nodes to split ', nodes_to_split)
            calc_chop = lambda x: int(0.85*(x[1]-x[0])+x[0])
            split_at = [calc_chop(traversed[k]['bounds']) for k in nodes_to_split]
            print(split_at)
            for s in split_at:
                print('add min', s, masked_Z[s])
                t.add_min(s, masked_Z[s], ignore_prom=True)
            print(t)
            traversed = coords_to_id(list(traverse(t, [0])))

            for i in traversed.keys():
                moments, _ = calc_moments(spectrum, traversed[i]['bounds'], traversed[i]['thres'])
                traversed[i].update(moments)
                if i in nodes_with_min:
                    traversed[i]['chop'] = True
            print(traversed)

    else:
        traversed = {}
    return traversed


def saveVar(dataset, varData, dtype=np.float32):
    """save an item to the dataset with data in a dict

    Args:
        dataset (:obj:netCDF4.Dataset): netcdf4 Dataset to add to
        dtype: datatype of the array
        varData (dict): data to add, for example:

    ================== ======================================================
     Key                Description
    ================== ======================================================
    ``var_name``        name of the variable
    ``dimension``       ``('time', 'height')``
    ``arr``             data
    ``long_name``       descriptive long name
    **optional**
    ``comment``         description as a sentence
    ``units``           string with units
    ``units_html``      units in the html formatting
    ``missing_value``   define missing value
    ``plot_range``      tuple of range to plot
    ``plot_scale``      "linear" or "log" 
    ``axis``            
    ================== ======================================================
    """
    item = dataset.createVariable(varData['var_name'], dtype, varData['dimension'])
    item[:] = varData['arr']
    item.long_name = varData['long_name']
    if 'comment' in varData.keys():
        item.comment = varData['comment']
    if 'units' in varData.keys():
        item.units = varData['units']
    if 'units_html' in varData.keys():
        item.units_html = varData['units_html']
    if 'missing_value' in varData.keys():
        item.missing_value = varData['missing_value']
    if 'plot_range' in varData.keys():
        item.plot_range = varData['plot_range']
    if 'plot_scale' in varData.keys():
        item.plot_scale = varData['plot_scale']
    if 'axis' in varData.keys():
        item.axis = varData['axis']


def get_git_hash():
    """
    Returns:
        git describe string
    """
    label = subprocess.check_output(['git', 'describe', '--always'])
    return label.rstrip()


def time_index(timestamps, sel_ts):
    """get the index of a timestamp in the list
    
    Args:
        timestamps: array
        sel_ts: timestamp whose index is required
    """
    return np.where(timestamps == min(timestamps, key=lambda t: abs(sel_ts - t)))[0][0]


def get_time_grid(timestamps, ts_range, time_interval, filter_empty=True):
    """get the mapping from timestamp indices to gridded times
    eg for use in interpolation routines

    TODO link to gist
    
    Args:
        timestamps: list of timestamps
        ts_range: range fo the gridded timestamps
        time_interval: interval of the gridded timestamps
        filter_empty (bool, optional): include the bins that are empty
    Returns:
        list of (timestamp_begin, timestamp_end, grid_mid, index_begin, index_end, no_indices)
    """
    grid = np.arange(ts_range[0], ts_range[1]+1, time_interval)
    grid_mid = grid[:-1] + np.diff(grid)/2

    corresponding_grid = np.digitize(timestamps, grid)-1
    bincount = np.bincount(corresponding_grid)
    end_index = np.cumsum(bincount)
    begin_index = end_index - bincount
    
    out = zip(grid[:-1], grid[1:], grid_mid, begin_index, end_index, bincount)
    if filter_empty:
        out = filter(lambda x: x[5] !=0, out)
    out = list(out)
    return [np.array(list(map(lambda e: e[i], out))) for i in range(6)]


class peakTreeBuffer():
    """trees for a time-height chunk

    Args:
        system (string): specify the system/campaign

    The attribute setting may contain
    
    ==================== ========================================================
     Key                  Description
    ==================== ========================================================
    ``decoupling``        decoupling of the crosschannel
    ``smooth``            flag if smoothing should be applied
    ``grid_time``         time in seconds to average the spectra
    ``max_no_nodes``      number of nodes to save
    ``thres_factor_co``   factor between noise_lvl and noise thres in co channel
    ``thres_factor_cx``   factor between noise_lvl and noise thres in cross ch.
    ``station_altitude``  height of station above msl
    ==================== ========================================================
    
    """
    def __init__(self, system="Lacros"):
        self.system = system
        if system == "Lacros":
            self.settings = {'decoupling': -30,
                            'smooth': True,
                            'grid_time': 6,
                            'max_no_nodes': 15,
                            'thres_factor_co': 3.0,
                            'thres_factor_cx': 3.0,
                            'LDR?': True,
                            'station_altitude': 12}
            self.location = 'Limassol'
            self.shortname = "Lim"
        elif system == "Lacros_at_ACCEPT":
            self.settings = {'decoupling': -30,
                            'smooth': True,
                            'grid_time': 5,
                            'max_no_nodes': 15,
        # TODO try with a smaller factor noise threshold is good with this dataset
                            'thres_factor_co': 1.2,
                            'thres_factor_cx': 1.2,
                            'LDR?': True,
                            'station_altitude': 12}
            self.location = 'Cabauw'
            self.shortname = "Cab"
        elif system == "Polarstern":
            self.settings = {'decoupling': -27,
                            'smooth': True,
                            'grid_time': 10,
                            'max_no_nodes': 15,
                            'thres_factor_co': 3.0,
                            'thres_factor_cx': 3.0,
                            'LDR?': True,
                            'station_altitude': 12}
            self.location = 'Polarstern'
            self.shortname = "Pol"
        elif system == "Lindenberg":
            self.settings = {'decoupling': -25,
                            'smooth': True,
                            'grid_time': False,
                            'max_no_nodes': 15,
                            'thres_factor_co': 3.0,
                            'thres_factor_cx': 3.0,
                            'LDR?': True,
                            'station_altitude': 100}
            self.location = 'Lindenberg'
            self.shortname = "Lin"
        else:
            raise ValueError('no system defined')


    def load_spec_file(self, filename):
        """load spectra from raw file
        
        Args:
            filename: specify file
        """
        self.type = 'spec'

        self.f = netCDF4.Dataset(filename, 'r')
        print('keys ', self.f.variables.keys())

        self.timestamps = self.f.variables['time'][:]
        print('time ', self.timestamps[:10])
        self.delta_ts = np.mean(np.diff(self.timestamps)) if self.timestamps.shape[0] > 1 else 2.0
        self.range = self.f.variables['range'][:]
        print('range ', self.range[:10])
        self.velocity = self.f.variables['velocity'][:]
        print('velocity ', self.velocity[:10])
        print('Z chunking ', self.f.variables['Z'].chunking())

        self.begin_dt = h.ts_to_dt(self.timestamps[0])

    def load_peakTree_file(self, filename):
        """load preprocessed peakTree file
     
        Args:
            filename: specify file
        """
        self.type = 'peakTree'
        self.f = netCDF4.Dataset(filename, 'r')
        print('loaded file ', filename)
        print('keys ', self.f.variables.keys())
        self.timestamps = self.f.variables['timestamp'][:]
        self.delta_ts = np.mean(np.diff(self.timestamps)) if self.timestamps.shape[0] > 1 else 2.0
        self.range = self.f.variables['range'][:]
        self.no_nodes = self.f.variables['no_nodes'][:]

    #@profile
    def get_tree_at(self, sel_ts, sel_range, temporal_average=False, silent=False):
        """get a single tree
        either from the spectrum directly (prior call of load_spec_file())
        or from the pre-converted file (prior call of load_peakTree_file())

        Args:
            sel_ts (tuple or float): either value or (index, value)
            sel_range (tuple or float): either value or (index, value)
            temporal_average (optional): aberage over the interval 
                (tuple of bin in time dimension or number of seconds)
            silent: verbose output
        Returns:
            dictionary with all nodes and the parameters of each node
        """
        if type(sel_ts) is tuple and type(sel_range) is tuple:
            it, sel_ts = sel_ts
            ir, sel_range = sel_range
        else:
            it = time_index(self.timestamps, sel_ts)
            ir = np.where(self.range == min(self.range, key=lambda t: abs(sel_range - t)))[0][0]
        print('time ', it, h.ts_to_dt(self.timestamps[it]), self.timestamps[it], 'height', ir, self.range[ir]) if not silent else None
        assert np.abs(sel_ts - self.timestamps[it]) < self.delta_ts, 'timestamps more than '+str(self.delta_ts)+'s apart'
        #assert np.abs(sel_range - self.range[ir]) < 10, 'ranges more than 10m apart'

        if type(temporal_average) is tuple:
            it_b, it_e = temporal_average
        elif temporal_average:
            it_b = time_index(self.timestamps, sel_ts-temporal_average/2.)
            it_e = time_index(self.timestamps, sel_ts+temporal_average/2.)
            assert self.timestamps[it_e] - self.timestamps[it_b] < 15, 'found averaging range too large'
            print('timerange ', it_b, h.ts_to_dt(self.timestamps[it_b]), it_e, h.ts_to_dt(self.timestamps[it_e])) if not silent else None

        if self.type == 'spec':
            decoupling = self.settings['decoupling']

            # why is ravel necessary here?
            # flatten seems to faster
            if not temporal_average:
                specZ = self.f.variables['Z'][:,ir,it].ravel()
                specZ_mask = specZ == 0.
                #print('specZ.shape', specZ.shape, specZ)
                specLDR = self.f.variables['LDR'][:,ir,it].ravel()
                specLDR_mask = np.isnan(specLDR)
                specZcx = specZ*specLDR
                specZcx_mask = np.logical_or(specZ_mask, specLDR_mask)
                specSNRco = self.f.variables['SNRco'][:,ir,it].ravel()
                specSNRco_mask = specSNRco == 0.
                no_averages = 1
            else: 
                specZ = self.f.variables['Z'][:,ir,it_b:it_e+1]
                no_averages = specZ.shape[1]
                specLDR = self.f.variables['LDR'][:,ir,it_b:it_e+1]
                specZcx = specZ*specLDR
                specZcx = np.average(specZcx, axis=1)
                specZ = np.average(specZ, axis=1)

                specLDR = specZcx/specZ
                specZ_mask = np.logical_or(~np.isfinite(specZ), specZ == 0)
                specZcx_mask = np.logical_or(~np.isfinite(specZ), ~np.isfinite(specZcx))

                specLDR_mask = np.logical_or(specZ == 0, ~np.isfinite(specLDR))
                
                specSNRco = self.f.variables['SNRco'][:,ir,it_b:it_e+1]
                specSNRco = np.average(specSNRco, axis=1)
                specSNRco_mask = specSNRco == 0.
                # print('specZ', specZ.shape, specZ)
                # print('specLDR', specLDR.shape, specLDR)
                # print('specSNRco', specSNRco.shape, specSNRco)

            #specSNRco = np.ma.masked_equal(specSNRco, 0)
            noise_thres = 1e-25 if np.all(specZ_mask) else specZ[~specZ_mask].min()*h.z2lin(self.settings['thres_factor_co'])
            if self.settings['smooth']:
                #print('smoothed spectrum')
                specZ = np.convolve(specZ, np.array([0.5,1,0.5])/2.0, mode='same')
            
            spectrum = {'ts': self.timestamps[it], 'range': self.range[ir], 'vel': self.velocity,
                        'specZ': specZ[::-1], 'noise_thres': noise_thres, 'no_temp_avg': no_averages}
            
            spectrum['specZ_mask'] = specZ_mask[::-1]
            spectrum['specSNRco'] = specSNRco[::-1]
            spectrum['specSNRco_mask'] = specSNRco_mask[::-1]
            spectrum['specLDR'] = specLDR[::-1]
            spectrum['specLDR_mask'] = specLDR_mask[::-1]
            
            spectrum['specZcx'] = specZcx[::-1]
            # spectrum['specZcx_mask'] = np.logical_or(spectrum['specZ_mask'], spectrum['specLDR_mask'])
            spectrum['specZcx_mask'] =  specZcx_mask[::-1]

            # print('test specZcx calc')
            # print(spectrum['specZcx_mask'])
            # print(spectrum['specZcx'])
            spectrum['specSNRcx'] = spectrum['specSNRco']*spectrum['specLDR']
            spectrum['specSNRcx_mask'] = np.logical_or(spectrum['specSNRco_mask'], spectrum['specLDR_mask'])

            thres_Zcx = np.nanmin(spectrum['specZcx'])*h.z2lin(self.settings['thres_factor_cx'])
            Zcx_mask = np.logical_or(spectrum['specZcx'] < thres_Zcx, ~np.isfinite(spectrum['specZcx']))
            spectrum['specLDRmasked'] = spectrum['specLDR'].copy()
            spectrum['specLDRmasked'][Zcx_mask] = np.nan

            spectrum['specZcx_mask'] = Zcx_mask
            spectrum['specZcx_validcx'] = spectrum['specZcx'].copy()
            spectrum['specZcx_validcx'][Zcx_mask] = 0.0
            spectrum['specZ_validcx'] = spectrum['specZ'].copy()
            spectrum['specZcx_validcx'][Zcx_mask] = 0.0

            spectrum['decoupling'] = decoupling
            #                                     deep copy of dict 
            travtree = tree_from_spectrum({**spectrum})

            return travtree, spectrum

        elif self.type == 'peakTree':
            settings_file = ast.literal_eval(self.f.settings)
            self.settings['max_no_nodes'] = settings_file['max_no_nodes']
            print('load tree from peakTree; no_nodes ', self.no_nodes[it,ir]) if not silent else None
            travtree = {}            
            print('peakTree parent', self.f.variables['parent'][it,ir,:]) if not silent else None

            print(np.argwhere(~self.f.variables['parent'][it,ir,:].mask).ravel()) if not silent else None
            avail_nodes = np.argwhere(~self.f.variables['parent'][it,ir,:].mask).ravel()
            for k in avail_nodes.tolist():
                #print('k', k)
                #(['timestamp', 'range', 'Z', 'v', 'width', 'LDR', 'skew', 'minv', 'maxv', 'threshold', 'parent', 'no_nodes']
                node = {'parent_id': int(np.asscalar(self.f.variables['parent'][it,ir,k])), 
                        'thres': h.z2lin(np.asscalar(self.f.variables['threshold'][it,ir,k])), 
                        'width': np.asscalar(self.f.variables['width'][it,ir,k]), 
                        #'bounds': self.f.variables[''][it,ir], 
                        'z': h.z2lin(np.asscalar(self.f.variables['Z'][it,ir,k])), 
                        'bounds': (np.asscalar(self.f.variables['bound_l'][it,ir,k]), np.asscalar(self.f.variables['bound_r'][it,ir,k])),
                        #'coords': [0], 
                        'skew': np.asscalar(self.f.variables['skew'][it,ir,k]),
                        'prominence': h.z2lin(np.asscalar(self.f.variables['prominence'][it,ir,k])),
                        'v': np.asscalar(self.f.variables['v'][it,ir,k])}
                if 'LDR' in self.f.variables.keys():
                    node['ldr'] = h.z2lin(np.asscalar(self.f.variables['LDR'][it,ir,k]))
                    node['ldrmax'] =  h.z2lin(np.asscalar(self.f.variables['ldrmax'][it,ir,k]))
                else:
                    node['ldr'], node['ldrmax'] = -99, -99
                if node['parent_id'] != -999:
                    if k == 0:
                        node['coords'] = [0]
                    else:
                        coords = travtree[node['parent_id']]['coords']
                        if k%2 == 0:
                            node['coords'] = coords + [1]
                        else:
                            node['coords'] = coords + [0]
                        #siblings = list(filter(lambda d: d['coords'][:-1] == coords, travtree.values()))
                        # #print('parent_id', node['parent_id'], 'siblings ', siblings)
                        #node['coords'] = coords + [len(siblings)]
                    travtree[k] = node

            return travtree, None

    #@profile
    def assemble_time_height(self, outdir):
        """convert a whole spectra file to the peakTree node file
        
        Args:
            outdir: directory for the output
        """
        #self.timestamps = self.timestamps[:10]

        if self.settings['grid_time']:
            time_grid = get_time_grid(self.timestamps, (self.timestamps[0], self.timestamps[-1]), self.settings['grid_time'])
            timestamps_grid = time_grid[2]
        else:
            timestamps_grid = self.timestamps

        max_no_nodes=self.settings['max_no_nodes']
        Z = np.zeros((timestamps_grid.shape[0], self.range.shape[0], max_no_nodes))
        Z[:] = -999
        v = Z.copy()
        width = Z.copy()
        LDR = Z.copy()
        skew = Z.copy()
        bound_l = Z.copy()
        bound_r = Z.copy()
        parent = Z.copy()
        thres = Z.copy()
        ldrmax = Z.copy()
        prominence = Z.copy()
        no_nodes = np.zeros((timestamps_grid.shape[0], self.range.shape[0]))

        for it, ts in enumerate(timestamps_grid[:]):
            print('it, ts', it, ts)
            it_radar = time_index(self.timestamps, ts)
            print('time ', it, h.ts_to_dt(timestamps_grid[it]), timestamps_grid[it], 'radar ', h.ts_to_dt(self.timestamps[it_radar]), self.timestamps[it_radar])
            if self.settings['grid_time']:
                temp_avg = time_grid[3][it], time_grid[4][it]
                print("temp_avg", temp_avg)

            for ir, rg in enumerate(self.range[:]):
                print(h.ts_to_dt(timestamps_grid[it]), ir, rg)
                #travtree, _ = self.get_tree_at(ts, rg, silent=True)
                if self.settings['grid_time']:
                    travtree, _ = self.get_tree_at((it_radar, self.timestamps[it_radar]), (ir, rg), temporal_average=temp_avg, silent=True)
                else:
                    travtree, _ = self.get_tree_at((it_radar, self.timestamps[it_radar]), (ir, rg), silent=True)


                node_ids = list(travtree.keys())
                nodes_to_save = [i for i in node_ids if i < max_no_nodes]
                no_nodes[it,ir] = len(node_ids)
                #print('max_no_nodes ', max_no_nodes, no_nodes[it,ir], list(travtree.keys()))
                for k in nodes_to_save:
                    if k in travtree.keys():
                        val = travtree[k]
                        #print(k,val)
                        Z[it,ir,k] = h.lin2z(val['z'])
                        v[it,ir,k] = val['v']
                        width[it,ir,k] = val['width']
                        LDR[it,ir,k] = h.lin2z(val['ldr'])
                        skew[it,ir,k] = val['skew']
                        bound_l[it,ir,k] = val['bounds'][0]
                        bound_r[it,ir,k] = val['bounds'][1]
                        parent[it,ir,k] = val['parent_id']
                        thres[it,ir,k] = h.lin2z(val['thres'])
                        ldrmax[it,ir,k] = h.lin2z(val['ldrmax'])
                        prominence[it,ir,k] = h.lin2z(val['prominence'])

        filename = outdir + '{}_{}_peakTree.nc4'.format(self.begin_dt.strftime('%Y%m%d_%H%M'),
                                                        self.shortname)
        print('output filename ', filename)
        
        with netCDF4.Dataset(filename, 'w', format='NETCDF4') as dataset:
            dim_time = dataset.createDimension('time', Z.shape[0])
            dim_range = dataset.createDimension('range', Z.shape[1])
            dim_nodes = dataset.createDimension('nodes', Z.shape[2])
            dim_nodes = dataset.createDimension('vel', self.velocity.shape[0])
            dataset.createDimension('mode', 1)

            times = dataset.createVariable('timestamp', np.int32, ('time',))
            times[:] = timestamps_grid.astype(np.int32)
            times.long_name = 'Unix timestamp [s]'

            dt_list = [h.ts_to_dt(ts) for ts in timestamps_grid]
            hours_cn = np.array([dt.hour + dt.minute / 60. + dt.second / 3600. for dt in dt_list])
            times_cn = dataset.createVariable('time', np.float32, ('time',))
            times_cn[:] = hours_cn.astype(np.float32)
            times_cn.units = "hours since " + self.begin_dt.strftime('%Y-%m-%d') + " 00:00:00 +00:00"
            times_cn.long_name = "Decimal hours from midnight UTC"
            times_cn.axis = "T"

            rg = dataset.createVariable('range', np.float32, ('range',))
            rg[:] = self.range.astype(np.float32)
            rg.long_name = 'range [m]'

            height = self.range + self.settings['station_altitude']
            hg = dataset.createVariable('height', np.float32, ('range',))
            hg[:] = height
            hg.long_name = 'Height above mean sea level [m]'

            vel = dataset.createVariable('velocity', np.float32, ('vel',))
            vel[:] = self.velocity.astype(np.float32)
            vel.long_name = 'velocity [m/s]'

            saveVar(dataset, {'var_name': 'Z', 'dimension': ('time', 'range', 'nodes'),
                              'arr': Z[:], 'long_name': "Reflectivity factor",
                              #'comment': "",
                              'units': "dBZ", 'missing_value': -999., 'plot_range': (-50., 20.),
                              'plot_scale': "linear"})
            saveVar(dataset, {'var_name': 'v', 'dimension': ('time', 'range', 'nodes'),
                              'arr': v[:], 'long_name': "Velocity",
                              #'comment': "Reflectivity",
                              'units': "m s-1", 'missing_value': -999., 'plot_range': (-8., 8.),
                              'plot_scale': "linear"})
            saveVar(dataset, {'var_name': 'width', 'dimension': ('time', 'range', 'nodes'),
                              'arr': width[:], 'long_name': "Spectral width",
                              #'comment': "Reflectivity",
                              'units': "m s-1", 'missing_value': -999., 'plot_range': (0.01, 3),
                              'plot_scale': "linear"})
            saveVar(dataset, {'var_name': 'skew', 'dimension': ('time', 'range', 'nodes'),
                              'arr': skew[:], 'long_name': "Skewness",
                              #'comment': "",
                              'units': '', 'missing_value': -999., 'plot_range': (-2., 2.),
                              'plot_scale': "linear"})
            saveVar(dataset, {'var_name': 'bound_l', 'dimension': ('time', 'range', 'nodes'),
                              'arr': bound_l[:].astype(np.int32), 'long_name': "Left bound of peak", #'comment': "",
                              'units': "bin", 'missing_value': -999., 'plot_range': (0, self.velocity.shape[0]),
                              'plot_scale': "linear"}, dtype=np.int32)
            saveVar(dataset, {'var_name': 'bound_r', 'dimension': ('time', 'range', 'nodes'),
                              'arr': bound_r[:].astype(np.int32), 'long_name': "Right bound of peak", #'comment': "",
                              'units': "bin", 'missing_value': -999., 'plot_range': (0, self.velocity.shape[0]),
                              'plot_scale': "linear"}, dtype=np.int32)
            saveVar(dataset, {'var_name': 'threshold', 'dimension': ('time', 'range', 'nodes'),
                              'arr': thres[:], 'long_name': "Subpeak Threshold",
                              #'comment': "",
                              'units': "dBZ", 'missing_value': -999., 'plot_range': (-50., 20.),
                              'plot_scale': "linear"})
            saveVar(dataset, {'var_name': 'parent', 'dimension': ('time', 'range', 'nodes'),
                              'arr': parent[:], 'long_name': "Index of the parent node",
                              #'comment': "",
                              'units': "", 'missing_value': -999., 'plot_range': (0, max_no_nodes),
                              'plot_scale': "linear"})
            if self.settings['LDR?']:
                saveVar(dataset, {'var_name': 'decoupling', 'dimension': ('mode'),
                                'arr':  self.settings['decoupling'], 'long_name': "LDR decoupling",
                                'units': "dB", 'missing_value': -999.})
                saveVar(dataset, {'var_name': 'LDR', 'dimension': ('time', 'range', 'nodes'),
                                'arr': LDR[:], 'long_name': "Linear depolarization ratio",
                                #'comment': "",
                                'units': "dB", 'missing_value': -999., 'plot_range': (-25., 0.),
                                'plot_scale': "linear"})
                saveVar(dataset, {'var_name': 'ldrmax', 'dimension': ('time', 'range', 'nodes'),
                                'arr': ldrmax[:], 'long_name': "Maximum LDR from SNR",
                                #'comment': "",
                                'units': "", 'missing_value': -999., 'plot_range': (-50., 20.),
                                'plot_scale': "linear"})
            saveVar(dataset, {'var_name': 'prominence', 'dimension': ('time', 'range', 'nodes'),
                              'arr': prominence[:], 'long_name': "Prominence of Peak above threshold",
                              #'comment': "",
                              'units': "", 'missing_value': -999., 'plot_range': (-50., 20.),
                              'plot_scale': "linear"})
            
            saveVar(dataset, {'var_name': 'no_nodes', 'dimension': ('time', 'range'),
                              'arr': no_nodes[:].copy(), 'long_name': "Number of detected nodes",
                              #'comment': "",
                              'units': "", 'missing_value': -999., 'plot_range': (0, max_no_nodes),
                              'plot_scale': "linear"})

            with open('output_meta.toml') as output_meta:
                meta_info = toml.loads(output_meta.read())

            dataset.description = 'peakTree processing'
            dataset.location = self.location
            dataset.institution = meta_info["institution"]
            dataset.contact = meta_info["contact"]
            dataset.creation_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
            dataset.settings = str(self.settings)
            dataset.commit_id = get_git_hash()
            dataset.day = str(self.begin_dt.day)
            dataset.month = str(self.begin_dt.month)
            dataset.year = str(self.begin_dt.year)


    def __del__(self):
        if 'f' in list(self.__dict__):
            self.f.close()




if __name__ == "__main__":
    # pTB = peakTreeBuffer()
    # pTB.load_spec_file('../data/D20150617_T0000_0000_Lin_zspc2nc_v1_02_standard.nc4')
    # pTB.get_tree_at(1434574800, 4910)

    pTB = peakTreeBuffer()
    pTB.load_spec_file('../data/D20170311_T2000_2100_Lim_zspc2nc_v1_02_standard.nc4')
    pTB.assemble_time_height('../output/')

    # pTB.load_peakTree_file('../output/20170311_2000_peakTree.nc4')
    # pTB.get_tree_at(1489262634, 3300)

    exit()
    # test the reconstruction:
    ts = 1489262404
    rg = 3300
    #rg = 4000
    #rg = 4100

    pTB = peakTreeBuffer()
    pTB.load_spec_file('../data/D20170311_T2000_2100_Lim_zspc2nc_v1_02_standard.nc4')
    tree_spec, _ = pTB.get_tree_at(ts, rg)
    
    print('del and load new')
    del pTB
    pTB = peakTreeBuffer()
    pTB.load_peakTree_file('../output/20170311_2000_peakTree.nc4')
    tree_file, _ = pTB.get_tree_at(ts, rg)

    print(list(map(lambda elem: (elem[0], elem[1]['coords']), tree_spec.items())))
    print(list(map(lambda elem: (elem[0], elem[1]['coords']), tree_file.items())))
    
    print(list(map(lambda elem: (elem[0], elem[1]['parent_id']), tree_spec.items())))
    print(list(map(lambda elem: (elem[0], elem[1]['parent_id']), tree_file.items())))

    print(list(map(lambda elem: (elem[0], elem[1]['v']), tree_spec.items())))
    print(list(map(lambda elem: (elem[0], elem[1]['v']), tree_file.items())))