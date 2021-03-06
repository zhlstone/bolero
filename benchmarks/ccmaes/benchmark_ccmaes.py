import os
import pickle
import numpy as np
import matplotlib.pyplot as plt
from joblib import Parallel, delayed
from bolero.optimizer import CCMAESOptimizer, CREPSOptimizer
from objective import Sphere, Rosenbrock


n_jobs = 4
result_file = "results.pickle"

objective_functions = {
    "sphere" : Sphere,
    "rosenbrock": Rosenbrock
}
algorithms = {
    "C-CMA-ES": CCMAESOptimizer,
    "C-REPS": CREPSOptimizer
}
seeds = list(range(20))

n_samples_per_update = 50
additional_ctor_args = {
    "C-CMA-ES": {
        "baseline_degree": 2
    },
    "C-REPS": {
        "train_freq": n_samples_per_update,
        "epsilon": 1.0,
        "min_eta": 1e-10  # 1e-20 in the original code
    }
}
n_params = 20
context_dims_per_objective = {
    "sphere": 2,
    "rosenbrock": 1
}
n_episodes_per_objective = {
    "sphere": 200 * n_samples_per_update,
    "rosenbrock": 850 * n_samples_per_update
}


def benchmark():
    """Run benchmarks for all configurations of objective and algorithm."""
    results = dict(
        (objective_name,
         dict((algorithm_name, [])
              for algorithm_name in algorithms.keys()))
        for objective_name in objective_functions.keys()
    )
    for objective_name in objective_functions.keys():
        for algorithm_name in algorithms.keys():
            feedbacks = Parallel(n_jobs=n_jobs, verbose=10)(
                delayed(optimize)(objective_name, algorithm_name, seed)
                for run_idx, seed in enumerate(seeds))
            results[objective_name][algorithm_name] = feedbacks
    return results


def optimize(objective_name, algorithm_name, seed):
    """Perform one benchmark run."""
    n_context_dims = context_dims_per_objective[objective_name]
    n_episodes = n_episodes_per_objective[objective_name]
    random_state = np.random.RandomState(seed)
    # contexts are sampled uniformly from 1 <= s <= 2 (here: < 2)
    contexts = random_state.rand(n_episodes, n_context_dims) + 1.0
    obj = objective_functions[objective_name](random_state, n_params, n_context_dims)
    initial_params = random_state.randn(n_params)
    opt = algorithms[algorithm_name](
        initial_params=initial_params,
        covariance=np.eye(n_params),
        variance=1.0,
        n_samples_per_update=n_samples_per_update,
        context_features="affine",
        random_state=random_state,
        gamma=1e-10,
        **additional_ctor_args[algorithm_name]
    )
    opt.init(n_params, n_context_dims)

    feedbacks = np.empty(n_episodes)
    params = np.empty(n_params)
    for episode_idx in range(n_episodes):
        opt.set_context(contexts[episode_idx])
        opt.get_next_parameters(params)
        feedbacks[episode_idx] = obj.feedback(
            params, contexts[episode_idx])
        opt.set_evaluation_feedback(feedbacks[episode_idx])

    return feedbacks


def show_results(results):
    """Display results."""
    for objective_name, objective_results in results.items():
        plt.figure()
        plt.title(objective_name)
        for algorithm_name, algorithm_results in objective_results.items():
            n_episodes = n_episodes_per_objective[objective_name]
            n_generations = n_episodes / n_samples_per_update
            grouped_feedbacks = np.array(algorithm_results).reshape(
                len(seeds), n_generations, n_samples_per_update)
            average_feedback_per_generation = grouped_feedbacks.mean(axis=2)
            mean_feedbacks = average_feedback_per_generation.mean(axis=0)
            std_feedbacks = average_feedback_per_generation.std(axis=0)
            generation = np.arange(n_generations) + 1.0
            m, l, u = _log_transform(mean_feedbacks, std_feedbacks)
            plt.plot(generation, m, label=algorithm_name)
            plt.fill_between(generation, l, u, alpha=0.5)
            yticks_labels = map(lambda t: "$-10^{%d}$" % -t, range(-5, 7))
            plt.yticks(range(-5, 7), yticks_labels)
            plt.xlabel("Generation")
            plt.ylabel("Average Return")
            plt.xlim((0, n_generations))
            plt.legend()
            plt.savefig(objective_name + "_plot.png")
    plt.show()


def _log_transform(mean_feedbacks, std_feedbacks):
    m = mean_feedbacks
    l = m - std_feedbacks
    m_log = -np.log10(-m)
    l_log = -np.log10(-l)
    # this is a hack: mean + std usually does not have the same distance to
    # the mean like mean - std in a log-scaled plot!
    u_log = m_log + (m_log - l_log)
    return m_log, l_log, u_log


if __name__ == "__main__":
    if os.path.exists(result_file):
        with open(result_file, "r") as f:
            results = pickle.load(f)
    else:
        results = benchmark()
        with open(result_file, "w") as f:
            pickle.dump(results, f)
    show_results(results)
