import sys

sys.path.append("..")

import random
import numpy as np
import math
import matplotlib.pyplot as plt
from scipy.stats import norm
from script_engine_utils import dist

'''
2 types : 
both
    - fixed increment changes, specific dists that are never hit
    - more likely to be faster earlier and then slow down

slow drag
    - especially if one axis xy has much less distance to travel relatively
    - appears to be a markov
fast drag
    - appears to be semi brownian with a trendline type thing?
    - fast increase and then slow decrease with lots of randomness
'''




class ClickPathGenerator:
    def __init__(self, x_increment, y_increment, x_max, y_max, deviation_degree, deviation_probability):
        self.x_increment = x_increment
        self.y_increment = y_increment
        self.x_max = x_max
        self.y_max = y_max
        self.deviation_degree = deviation_degree
        self.deviation_probability = deviation_probability

    @staticmethod
    def generate_delta_function(source_point_x, source_point_y, target_point_x, target_point_y):
        init_angle = math.atan(abs(target_point_y - source_point_y) / (abs(target_point_x - source_point_x) + 1e-6))
        point_dist_x = (target_point_x - source_point_x)
        point_dist_y = (target_point_y - source_point_y)
        point_dist = math.sqrt(point_dist_x ** 2 + point_dist_y ** 2)
        sign_x = -1 if point_dist_x < 0 else 1
        sign_y = -1 if point_dist_y < 0 else 1
        delta_x = lambda diff,time: math.cos(init_angle + diff) * sign_x * point_dist * time
        delta_y = lambda diff,time: math.sin(init_angle + diff) * sign_y * point_dist * time
        return delta_x,delta_y

    @staticmethod
    def map_delta_val(delta, increment, is_delta_x):
        intermediate_point_odds = 0 # random.random()
        floored_map_val_index = random.randint(0, 1)
        delta_over_increment = delta / increment
        delta_over_increment = 0 if np.isnan(delta_over_increment) else delta_over_increment
        discretized_delta = int(delta_over_increment)
        # delta_acc = delta - discretized_delta
        mapped_delta = discretized_delta * increment
        floored_mapped_delta = int(mapped_delta)
        has_remainder = mapped_delta - floored_mapped_delta > 0
        if floored_mapped_delta == 0:
            return 0,mapped_delta
        if is_delta_x:
            if has_remainder:
                map_val_choices = [floored_mapped_delta, floored_mapped_delta + 1]
            else:
                map_val_choices = [floored_mapped_delta - 1, floored_mapped_delta]
        else:
            map_val_choices = [floored_mapped_delta, floored_mapped_delta + 1]
        if intermediate_point_odds < 0.1:
            final_mapped_delta = map_val_choices[floored_map_val_index] - 30
        else:
            final_mapped_delta = map_val_choices[floored_map_val_index]
        d_delta_acc = (delta - final_mapped_delta)
        return final_mapped_delta,d_delta_acc

    @staticmethod
    def discretize_deltalist(deltalist, max_val, increment, is_delta_x):
        delta_acc = 0
        discretized_deltalist = []
        deltalist = list(map(lambda val: val * max_val, deltalist))
        for delta in deltalist:
            append_val = 0
            if abs(delta_acc) > int(increment + 1):
                mapped_delta_acc, d_delta_acc = ClickPathGenerator.map_delta_val(delta_acc, increment, is_delta_x)
                delta_acc = delta_acc - mapped_delta_acc + d_delta_acc
                append_val = mapped_delta_acc
            mapped_delta_val, d_delta_acc = ClickPathGenerator.map_delta_val(delta, increment, is_delta_x)
            delta_acc += d_delta_acc
            if mapped_delta_val == 0:
                discretized_deltalist.append(mapped_delta_val)
                delta_acc += append_val
            else:
                discretized_deltalist.append(mapped_delta_val + append_val)
        return discretized_deltalist

    @staticmethod
    def generate_speed_path(length, plot=False, max_speed=5):
        init_speed = random.randint(1, max_speed)
        acceleration_time = random.randint(2, 6)
        n_deltas = length
        transition_matrix = np.zeros((10))
        transition_choices = np.arange(0, 10)
        speed_sequence = []
        for step in range(0, n_deltas):
            transition_center = ((-init_speed / n_deltas * step + init_speed) * min(step / acceleration_time, 1))
            prev_cdf = 0
            # print(transition_center)

            for transition_index in range(0, 10):
                curr_cdf = norm.cdf(transition_index, loc=transition_center)
                transition_matrix[transition_index] = curr_cdf - prev_cdf
                prev_cdf = curr_cdf
            transition_matrix /= transition_matrix.sum()
            # print(transition_matrix)
            speed_sequence.append(np.random.choice(transition_choices, p=transition_matrix))
        if plot:
            plt.plot(speed_sequence)
            plt.show()
        return speed_sequence

    @staticmethod
    def refit_delta_path(delta_path, max_val, increment, merge=True):
        refit_path = ClickPathGenerator.generate_speed_path(len(delta_path))
        delta_avg = sum(delta_path) / len(delta_path)
        refit_path = list(map(lambda delta: (delta * increment / max_val), refit_path))
        refit_avg = sum(refit_path) / len(refit_path)
        refit_path = list(map(lambda delta : delta / refit_avg * delta_avg, refit_path))
        if merge:
            return ClickPathGenerator.merge_refit_delta_path(delta_path, refit_path)
        else:
            return refit_path

    @staticmethod
    def merge_refit_delta_path(delta_path, refit_path, plot=False):
        signs = np.sign(delta_path)
        delta_path = list(map(abs, delta_path))
        n_deltas = len(delta_path)
        lookahead_index = 2
        for delta_index in range(0, n_deltas - lookahead_index):
            x_sum = sum(delta_path[delta_index : delta_index + lookahead_index])
            y_sum = sum(refit_path[delta_index : delta_index + lookahead_index])
            for delta_refit_index in range(0, lookahead_index):
                delta_path[delta_index] = refit_path[delta_index] + (x_sum - y_sum) / lookahead_index
            # maximize -(xn - yn)**2 + L(x1 + x2 + ... + xn - c)
            # -2xn + 2yn + L = 0 => xn =  yn + L / 2
            # (y1 + L / 2 ... yn + L / 2 - c) = 0
            # L= 2(c - sum (y_n)1..n) / n
            # x_i = y_i + (c- sum (y_i)) / n
        delta_path = delta_path * signs
        if plot:
            plt.plot(delta_path)
            plt.plot(refit_path)
            plt.show()
        return delta_path

    # TODO: not sure if program in general works with negative numbers
    # TODO : when you discretize make sure it cannot go off the edge
    # TODO : discretize returning -1 / -30 when things are 0
    def generate_path_from_sequence(self, sequence_x, sequence_y, sign_x, sign_y):
        seq_len = len(sequence_x)
        click_sequence_x = list(map(lambda val: val * sign_x, ClickPathGenerator.generate_speed_path(len(sequence_x), max_speed=2)))
        click_sequence_y = list(map(lambda val: val * sign_y, ClickPathGenerator.generate_speed_path(len(sequence_y), max_speed=2)))
        for sequence_index in range(0, seq_len):
            if sequence_x[sequence_index] != 0:
                click_sequence_x[sequence_index] *= (self.x_increment / self.x_max)
            else:
                click_sequence_x[sequence_index] = 0
            if sequence_y[sequence_index] != 0:
                click_sequence_y[sequence_index] *= (self.y_increment / self.y_max)
            else:
                click_sequence_y[sequence_index] = 0
        click_sequence_x = self.discretize_deltalist(click_sequence_x, self.x_max, self.x_increment, is_delta_x=True)
        click_sequence_y = self.discretize_deltalist(click_sequence_y, self.y_max, self.y_increment, is_delta_x=False)
        return click_sequence_x,click_sequence_y

    def generate_raw_path(self, source_point_x,source_point_y,target_point_x,target_point_y, deviation_degree, deviation_probability):
        target_source_dist = 1
        # log_file.write('source:\n')
        # log_file.write('\t' + str(source_point_x) + ',' + str(source_point_y) + '\n')
        # log_file.write('target:\n')
        # log_file.write('\t' + str(target_point_x) + ',' + str(target_point_y) + '\n')
        pointlist_x = [source_point_x]
        pointlist_y = [source_point_y]
        checkpoint_x = source_point_x
        checkpoint_y = source_point_y
        pathlist_x = [checkpoint_x]
        pathlist_y = [checkpoint_y]
        deltalist_x = []
        deltalist_y = []

        delta_x, delta_y = ClickPathGenerator.generate_delta_function(source_point_x, source_point_y, target_point_x,
                                                        target_point_y)
        delta_delta_x = 0
        delta_delta_y = 0
        acc_delta_x = 0
        acc_delta_y = 0
        delta_x_threshold = (self.x_increment / self.x_max)
        delta_y_threshold = (self.y_increment / self.y_max)
        accelerated_path = 0.6
        # correction_chance = 1 / (1.6 - self.deviation_probability)
        # n_steps = 100
        steps = 0
        delta_speed = 0
        markov_ratio = 0
        last_source_point_x, last_source_point_y = source_point_x, source_point_y
        init_speed = random.randint(1, 3) / 100
        acceleration_time = random.randint(2, 6)
        # log_file.write('points:\n')
        # sensitivity = target_source_dist / 100
        while target_source_dist > 2 * dist(source_point_x, source_point_y, last_source_point_x,
                                            last_source_point_y):
            if accelerated_path > 0.5:
                delta_speed = markov_ratio * delta_speed * (1 + (np.random.normal() / 25)) + (
                            1 - markov_ratio) * ((-init_speed / (2 / init_speed) * steps + init_speed) * min(
                    steps / acceleration_time, 1))
            else:
                delta_speed = 1 / 100
            if random.random() < deviation_probability:
                deviation_seed = 100
                while abs(deviation_seed) > 1:
                    deviation_seed = np.random.normal(scale=9.0)
                delta_delta_x += deviation_degree * (math.pi / 180) * deviation_seed
                delta_delta_y += deviation_degree * (math.pi / 180) * deviation_seed
            gravity_x, gravity_y = ClickPathGenerator.generate_delta_function(source_point_x, source_point_y, target_point_x,
                                                                target_point_y)

            last_source_point_x, last_source_point_y = source_point_x, source_point_y
            delta_path_x = (delta_x(delta_delta_x, max(delta_speed, 1 / 8000))) * 1 / math.log(steps + 2)
            delta_path_y = (delta_y(delta_delta_y, max(delta_speed, 1 / 8000))) * 1 / math.log(steps + 2)

            # d = (2 - 1 / n)

            source_point_x += delta_path_x
            source_point_y += delta_path_y
            target_source_dist = dist(source_point_x, source_point_y, target_point_x, target_point_y)
            delta_gravity_x = (gravity_x(0, max(delta_speed, 1 / 8000)) / (target_source_dist))
            delta_gravity_y = (gravity_y(0, max(delta_speed, 1 / 8000)) / (target_source_dist))
            # delta_gravity_x = (gravity_x(0, max(delta_speed, 1/200)) * (math.log(steps + 2)))
            # delta_gravity_y = (gravity_y(0, max(delta_speed, 1/200)) * (math.log(steps + 2)))

            source_point_x += delta_gravity_x
            source_point_y += delta_gravity_y
            target_source_dist = dist(source_point_x, source_point_y, target_point_x, target_point_y)
            # print(source_point_x, ',',source_point_y)
            curr_delta_x = delta_path_x + delta_gravity_x
            curr_delta_y = delta_path_y + delta_gravity_y
            x_below_threshold = abs(curr_delta_x + acc_delta_x) < delta_x_threshold
            y_below_threshold = abs(curr_delta_y + acc_delta_y) < delta_y_threshold
            # n_splits = 6

            if x_below_threshold and y_below_threshold:
                acc_delta_x += curr_delta_x
                acc_delta_y += curr_delta_y
            elif x_below_threshold:
                acc_delta_x += curr_delta_x
                pathlist_x.append(checkpoint_x)
                pathlist_y.append(checkpoint_y + curr_delta_y + acc_delta_y)

                deltalist_y.append((curr_delta_y + acc_delta_y))
                deltalist_x.append(0)
                acc_delta_y = 0
                checkpoint_y = source_point_y
            elif y_below_threshold:
                pathlist_x.append(checkpoint_x + curr_delta_x + acc_delta_x)
                acc_delta_x = 0
                checkpoint_x = source_point_x
                acc_delta_y += curr_delta_y
                pathlist_y.append(checkpoint_y)
                deltalist_x.append((curr_delta_x + acc_delta_x))
                deltalist_y.append(0)
            else:
                pathlist_x.append(checkpoint_x + curr_delta_x + acc_delta_x)
                pathlist_y.append(checkpoint_y + curr_delta_y + acc_delta_y)
                acc_delta_x = 0
                acc_delta_y = 0
                checkpoint_x = source_point_x
                checkpoint_y = source_point_y
                deltalist_y.append((curr_delta_y + acc_delta_y))
                deltalist_x.append((curr_delta_x + acc_delta_x))

            pointlist_x.append(source_point_x)
            pointlist_y.append(source_point_y)
            steps += 1
        # plt.plot(pointlist_x, pointlist_y)
        # plt.show()
        return deltalist_x, deltalist_y

    def generate_click_path(self, source_x,source_y,target_x,target_y):
        print('source: ({}, {}), target: ({}, {})'.format(source_x, source_y, target_x, target_y))
        deltalist_x,deltalist_y = self.generate_raw_path(source_x,source_y,target_x,target_y, self.deviation_degree, self.deviation_probability)
        refitted_path_x,refitted_path_y = self.refit_delta_path(deltalist_x, self.x_max, self.x_increment),self.refit_delta_path(deltalist_y, self.y_max, self.y_increment)
        discretized_delta_x,discretized_delta_y = self.discretize_deltalist(refitted_path_x, self.x_max, self.x_increment, is_delta_x=True), self.discretize_deltalist(refitted_path_y, self.y_max, self.y_increment, is_delta_x=False)
        # print(len(discretized_delta_x))
        # print(sum(discretized_delta_x))
        # print(len(discretized_delta_y))
        # print(sum(discretized_delta_y))
        # print(len(refitted_path_x))
        # print(len(refitted_path_y))
        # exit(0)
        # global last_val
        # last_val = 0
        #
        # def undeltize(val):
        #     global last_val
        #     val = val + last_val
        #     last_val = val
        #     return val
        #
        # print(sum(discretized_delta_x))
        # print(sum(discretized_delta_y))
        # print(len(discretized_delta_x))
        # print(len(discretized_delta_y))
        # pointized_x = list(map(undeltize, discretized_delta_x))
        # last_val = 0
        # pointized_y = list(map(undeltize, discretized_delta_y))
        # plt.plot(pointized_x, pointized_y)
        # plt.show()
        # exit(0)
        return discretized_delta_x, discretized_delta_y

if __name__=='__main__':
    path_generator = ClickPathGenerator(41, 71, 32726, 32726, 45, 0.4)
    x, y = path_generator.generate_click_path(0.1,0.1,0.9,0.9)
    plt.plot(y)
    plt.show()