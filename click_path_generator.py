import random
import numpy as np
import math
import matplotlib.pyplot as plt
from scipy.stats import norm

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



def dist(x1, y1, x2, y2):
    return math.sqrt((y2 - y1) ** 2 + (x2 - x1) ** 2)

def generate_delta_function(source_point_x, source_point_y, target_point_x, target_point_y):
    init_angle = math.atan(abs(target_point_y - source_point_y) / abs(target_point_x - source_point_x))
    point_dist_x = (target_point_x - source_point_x)
    point_dist_y = (target_point_y - source_point_y)
    point_dist = math.sqrt(point_dist_x ** 2 + point_dist_y ** 2)
    sign_x = -1 if point_dist_x < 0 else 1
    sign_y = -1 if point_dist_y < 0 else 1
    delta_x = lambda diff,time: math.cos(init_angle + diff) * sign_x * point_dist * time
    delta_y = lambda diff,time: math.sin(init_angle + diff) * sign_y * point_dist * time
    return delta_x,delta_y

def map_delta_val(delta, increment, is_delta_x):
    intermediate_point_odds = random.random()
    floored_map_val_index = random.randint(0, 1)
    discretized_delta = int(delta / increment)
    # delta_acc = delta - discretized_delta
    mapped_delta = discretized_delta * increment
    floored_mapped_delta = int(mapped_delta)
    has_remainder = discretized_delta - floored_mapped_delta > 0
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

def discretize_deltalist(deltalist, max_val, increment, is_delta_x):
    delta_acc = 0
    discretized_deltalist = []
    deltalist = list(map(lambda val: val * max_val, deltalist))
    for delta in deltalist:
        append_val = 0
        if delta_acc > int(increment + 1):
            mapped_delta_acc, d_delta_acc = map_delta_val(delta_acc, increment, is_delta_x)
            delta_acc = delta_acc - mapped_delta_acc + d_delta_acc
            append_val = mapped_delta_acc
        mapped_delta_val, d_delta_acc = map_delta_val(delta, increment, is_delta_x)
        delta_acc += d_delta_acc
        discretized_deltalist.append(mapped_delta_val + append_val)
    return discretized_deltalist

def generate_speed_path(length, plot=False):
    init_speed = random.randint(2, 5)
    acceleration_time = random.randint(2, 6)
    n_deltas = length
    transition_matrix = np.zeros((10))
    transition_choices = np.arange(0, 10)
    speed_sequence = []
    for step in range(0, n_deltas):
        transition_center = ((-init_speed / n_deltas * step + init_speed) * min(step / acceleration_time, 1))
        prev_cdf = 0
        print(transition_center)

        for transition_index in range(0, 10):
            curr_cdf = norm.cdf(transition_index, loc=transition_center)
            transition_matrix[transition_index] = curr_cdf - prev_cdf
            prev_cdf = curr_cdf
        transition_matrix /= transition_matrix.sum()
        print(transition_matrix)
        speed_sequence.append(np.random.choice(transition_choices, p=transition_matrix))
    if plot:
        plt.plot(speed_sequence)
        plt.show()
    return speed_sequence

def refit_delta_path(delta_path, max_val, increment):
    refit_path = generate_speed_path(len(delta_path))
    delta_avg = sum(delta_path) / len(delta_path)
    refit_path = list(map(lambda delta: (delta * increment / max_val), refit_path))
    refit_avg = sum(refit_path) / len(refit_path)
    refit_path = list(map(lambda delta : delta / refit_avg * delta_avg, refit_path))
    return merge_refit_delta_path(delta_path, refit_path)

def merge_refit_delta_path(delta_path, refit_path, plot=False):
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
    if plot:
        plt.plot(delta_path)
        plt.plot(refit_path)
        plt.show()
    return delta_path


def simulate_path(deviation_degree, deviation_chance, n_sims, plot=False):
    plot_title = str(deviation_degree) + '-' + str(deviation_chance)
    if plot:
        print(plot_title)
        plt.title(plot_title)
        one_plot = (n_sims == 1)
        if one_plot:
            fig, ax = plt.figure(dpi=150),plt.gca()
        else:
            fig, ax = plt.subplots(n_sims, n_sims, dpi=150)
    deltalists = []
    for sim_row_index in range(0, n_sims):
        deltalists.append([])
        for sim_col_index in range(0,n_sims):
            deltalists[sim_row_index].append([])
            # with open('./figs/' + plot_title + '-logfile-' + str(sim_row_index) + '-' + str(sim_col_index) + '.txt', 'w') as log_file:
            target_source_dist = 0
            x_dist = 0
            y_dist = 0
            while target_source_dist < 0.4 or x_dist < 0.1 or y_dist < 0.1:
                source_point_x = random.random()
                source_point_y = random.random()

                target_point_x = random.random()
                target_point_y = random.random()
                x_dist = abs(source_point_x - target_point_x)
                y_dist = abs(source_point_y - target_point_y)
                target_source_dist = dist(source_point_x, source_point_y, target_point_x, target_point_y)

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

            delta_x,delta_y = generate_delta_function(source_point_x,source_point_y,target_point_x,target_point_y)
            # print([sign_x, sign_y])
            # print([source_point_x, source_point_y])
            # print([target_point_x, target_point_y])
            # print([delta_x(0, 1/100), delta_y(0, 1/100)])
            # print(180 * init_angle / math.pi)
            if plot:
                if one_plot:
                    ax.plot(source_point_x, source_point_y, "bo")
                else:
                    ax[sim_row_index][sim_col_index].plot(source_point_x, source_point_y, "bo")
            delta_delta_x = 0
            delta_delta_y = 0
            acc_delta_x = 0
            acc_delta_y = 0
            delta_delta_decay = 0
            delta_x_threshold = 68.25 / 32726
            delta_y_threshold = 121.5 / 32726
            accelerated_path = 0.6
            correction_chance = 1 / (1.6 - deviation_chance)
            n_steps = 100
            steps = 0
            delta_speed = 0
            markov_ratio = 0
            last_source_point_x,last_source_point_y = source_point_x,source_point_y
            init_speed = random.randint(1, 3) / 100
            acceleration_time = random.randint(2, 6)
            # log_file.write('points:\n')
            sensitivity = target_source_dist / 100
            while target_source_dist > 2 * dist(source_point_x,source_point_y,last_source_point_x,last_source_point_y):
                if accelerated_path > 0.5:
                    delta_speed = markov_ratio * delta_speed * (1 + (np.random.normal()/25)) + (1 - markov_ratio) * ((-init_speed / (2 / init_speed) * steps + init_speed) * min(steps / acceleration_time, 1))
                else:
                    delta_speed = 1/100
                if random.random() < deviation_chance:
                    deviation_seed = 100
                    while abs(deviation_seed) > 1:
                        deviation_seed = np.random.normal(scale=9.0)
                    delta_delta_x += deviation_degree * (math.pi / 180) * deviation_seed
                    delta_delta_y += deviation_degree * (math.pi / 180) * deviation_seed
                gravity_x, gravity_y = generate_delta_function(source_point_x, source_point_y, target_point_x,target_point_y)
                last_source_point_x,last_source_point_y = source_point_x,source_point_y
                delta_path_x = (delta_x(delta_delta_x, max(delta_speed, 1/200))) * 1 / math.log(steps + 2)
                delta_path_y = (delta_y(delta_delta_y, max(delta_speed, 1/200))) * 1 / math.log(steps + 2)

                # d = (2 - 1 / n)

                source_point_x += delta_path_x
                source_point_y += delta_path_y
                delta_delta_x *= (1 - delta_delta_decay)
                delta_delta_y *= (1 - delta_delta_decay)
                target_source_dist = dist(source_point_x, source_point_y, target_point_x, target_point_y)
                delta_gravity_x = (gravity_x(0, max(delta_speed, 1/200)) / (target_source_dist))
                delta_gravity_y = (gravity_y(0, max(delta_speed, 1/200)) / (target_source_dist))
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
                if x_below_threshold and y_below_threshold:
                    acc_delta_x += curr_delta_x
                    acc_delta_y += curr_delta_y
                elif x_below_threshold:
                    acc_delta_x += curr_delta_x
                    pathlist_x.append(checkpoint_x)
                    pathlist_y.append(checkpoint_y + curr_delta_y + acc_delta_y)
                    deltalist_y.append(abs(curr_delta_y + acc_delta_y))
                    deltalist_x.append(0)
                    acc_delta_y = 0
                    checkpoint_y = source_point_y
                elif y_below_threshold:
                    pathlist_x.append(checkpoint_x + curr_delta_x + acc_delta_x)
                    acc_delta_x = 0
                    checkpoint_x = source_point_x
                    acc_delta_y += curr_delta_y
                    pathlist_y.append(checkpoint_y)
                    deltalist_x.append(abs(curr_delta_x + acc_delta_x))
                    deltalist_y.append(0)
                else:
                    pathlist_x.append(checkpoint_x + curr_delta_x + acc_delta_x)
                    pathlist_y.append(checkpoint_y + curr_delta_y + acc_delta_y)
                    acc_delta_x = 0
                    acc_delta_y = 0
                    checkpoint_x = source_point_x
                    checkpoint_y = source_point_y
                    deltalist_y.append(abs(curr_delta_y + acc_delta_y))
                    deltalist_x.append(abs(curr_delta_x + acc_delta_x))


                pointlist_x.append(source_point_x)
                pointlist_y.append(source_point_y)
                # log_file.write('\t' + str([delta_delta_x, delta_delta_y]) + ' ' + str([delta_x(delta_delta_x,1/n_steps), delta_y(delta_delta_y,1/n_steps)]) +'\n')
                # print(steps, [source_point_x, source_point_y], [delta_delta_x, delta_delta_y], [gravity_x(0, 1/n_steps), 1 / target_source_dist])
                # log_file.write('\t' + str(steps) + ': ' + str([source_point_x, source_point_y]) + ',' + str([delta_delta_x, delta_delta_y]) + ',' + str([gravity_x(0, 1/n_steps), 1 / target_source_dist]) + '\n')
                steps += 1
            print(deltalist_x)
            if plot:
                if one_plot:
                    ax.plot(pathlist_x, pathlist_y)
                    ax.plot(target_point_x, target_point_y, "or")
                else:
                    ax[sim_row_index][sim_col_index].plot(pathlist_x, pathlist_y)
                    ax[sim_row_index][sim_col_index].plot(target_point_x, target_point_y, "or")
                print(steps)
            else:
                return deltalist_x, deltalist_y
            # print(deltalist_x, deltalist_y)
            # print(pointlist_x, pointlist_y)
            # deltalist_x = avd_discretize(deltalist_x, 32767, 121.5, True)
            deltalists[sim_row_index][sim_col_index].append({
                "deltalist_x": deltalist_x,
                "deltalist_y": deltalist_y
            })
    if plot:
        plt.savefig('./figs/' + plot_title + '.png')
        plt.close()
    for row_index,deltalist_row in enumerate(deltalists):
        for col_index,deltalist_col in enumerate(deltalist_row):
            deltalist_col = deltalist_col[0]
            if plot:
                plt.plot(deltalist_col['deltalist_x'])
                plt.savefig('./figs/'+ plot_title + '-' + str(row_index) + '-' + str(col_index) + 'deltalist_x.png')
                plt.close()
                plt.plot(deltalist_col['deltalist_y'])
                plt.savefig('./figs/'+ plot_title + '-' + str(row_index) + '-' + str(col_index) + 'deltalist_y.png')
                plt.close()

# for deviation_degree_index in range(40, 65, 5): #8
#     deviation_degree = deviation_degree_index
#     for deviation_chance_index in range(3, 8): #6
#         deviation_chance = deviation_chance_index / 10
#         simulate_path(deviation_degree, deviation_chance, 4)

def generate_click_path(source_x,source_y,target_x,target_y):
    x_increment = 68.25
    y_increment = 121.5
    screen_max = 32726
    deltalist_x,deltalist_y = simulate_path(45, 0.4, 4, plot=False)
    # deltalist_x = [0.017249992426428412, 0.013614579092950538, 0.01232515739205823, 0.010172014910376862, 0.009905090948614822, 0.009721779728354134, 0.011657652032632436, 0.01141675289988003, 0.011219745048853976, 0.010627056154775804, 0.0105088424214889, 0.01083830226015718, 0.009591278270847095, 0.009539939395253192, 0.010342862307892345, 0.010612875435462226, 0.010526104767271928, 0.010444972940364419, 0.01036862366108458, 0.010296356431031072, 0.010227590947090992, 0.01016184085459812, 0.01009869407821127, 0.010037797861124955, 0.009363540728628932, 0.009335876424441125, 0.00930963773891335, 0.009284685197911523, 0.009849322832735227, 0.009797167570489498, 0.009745737579734667, 0.009694889341727353, 0.00964448888227117, 0.009343602683204246, 0.008579142477340243, 0.008525900951196281, 0.008872332018264642, 0.009360061762507792, 0.009311450130442366, 0.009262541594300528, 0.009213228025517982, 0.0090194710124314, 0.00892139755632276, 0.008628380370849344, 0.008608338751491723, 0.008588346838530067, 0.008568359811803934, 0.008548331538853704, 0.008528213989621364, 0.008041871763175279, 0.008042315972486572, 0.008623681320223658, 0.00859601504800944, 0.008567598586660275, 0.008319791511087995, 0.008304069969550486, 0.008809578962564686, 0.008736981724393033, 0.008659587216849611, 0.008576582835408922, 0.008485466734119469, 0.008377616504647875, 0.008255318900833636, 0.008119844137656106, 0.007968029560796647, 0.0076410436971889595, 0.007532904066073769, 0.0074307881416788716, 0.007115173488978263, 0.006717734264038065, 0.006189697639248433, 0.0055653427818724635]
    # deltalist_x = [0.00530489022016589, 0.004656926698004068, 0.004054676381235769, 0.0044099324739096755, 0.005523524675776872, 0.006527904410291234, 0.0062505372192142705, 0.006020641564134503, 0.005521775787755657, 0.005361905591160695, 0.00547878445949765, 0.0053379441590605155, 0.0049483251391994115, 0.005128640034363211, 0.0048724782129523445, 0.004776359272244689, 0.004683251454974711, 0.004587364292829487, 0.004495182129258786, 0.004406226169781268, 0.0044430753223515754, 0.00435799834288314, 0.004275168633336406, 0.004194329759371268, 0.00402602632682426, 0.0039558252793851275, 0.0038868579797601784, 0.0038189825225580596, 0.0035095254437664705, 0.0034713682348813733, 0.00341725954955062, 0.0033636715088920187, 0.003473253925272024, 0.0034122350387415217, 0.0033515768499447415, 0.0033910022853327914, 0.00329780420089914, 0.003233329295057167, 0.003168961398591087, 0.003139023600747835, 0.0030719520077227523, 0.0030047958973509637, 0.002937478753027147, 0.0028699212902866256, 0.002802040538458561, 0.0027372178841256643, 0.0026659584344095586, 0.00259419960774243, 0.0025218435500372104, 0.002371507852140657, 0.0023061474037804845, 0.002239678490965712, 0.002192540139053521, 0.0021160968580222, 0, 0.0019592669646147265, 0, 0.0017958495765041456, 0, 0.0016237884387100905, 0, 0.001440245741742951, 0, 0.0012509645273694305, 0, 0.0010537279937282277, 0, 0, 0.0006802238049597564, 0, 0, 0, 0]

    refitted_path_x,refitted_path_y = refit_delta_path(deltalist_x, screen_max, x_increment),refit_delta_path(deltalist_y, screen_max, y_increment)
    print(refitted_path_x)
    # plt.plot(refitted_path_x)
    # plt.show()
    # plt.plot(refitted_path_x)
    discretized_delta_x,discretized_delta_y = discretize_deltalist(refitted_path_x, screen_max, x_increment, is_delta_x=True),discretize_deltalist(refitted_path_y, screen_max, y_increment, is_delta_x=False)
    # plt.plot(discretized_delta_x)
    # plt.show()


