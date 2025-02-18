// Copyright (C) 2023 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//

#include "test_utils.h"

#include "intel_gpu/runtime/engine.hpp"

#include "intel_gpu/graph/program.hpp"
#include "data_inst.h"
#include "eltwise_inst.h"
#include "reshape_inst.h"
#include "shape_of_inst.h"
#include "fully_connected_inst.h"
#include "permute_inst.h"
#include "reduce_inst.h"
#include "intel_gpu/graph/network.hpp"
#include "pass_manager.h"
#include "to_string_utils.h"
#include <regex>
#include "program_wrapper.h"

#include <memory>

using namespace cldnn;
using namespace ::tests;

TEST(kernels_cache, reuse_kernel_for_static_model_01) {
    auto& engine = get_test_engine();

    auto input0 = engine.allocate_memory({{1, 1, 4, 5}, data_types::f16, format::bfyx});
    auto input1 = engine.allocate_memory({{1, 1, 4, 5}, data_types::f16, format::bfyx});
    auto input2 = engine.allocate_memory({{1, 1, 4, 5}, data_types::f16, format::bfyx});
    auto input3 = engine.allocate_memory({{1, 1, 4, 5}, data_types::f16, format::bfyx});
    auto input4 = engine.allocate_memory({{1, 1, 4, 5}, data_types::f16, format::bfyx});
    auto input5 = engine.allocate_memory({{1, 1, 4, 5}, data_types::f16, format::bfyx});
    auto weights1 = engine.allocate_memory({{1, 3, 2, 3 }, data_types::f16, format::bfyx});
    auto weights2 = engine.allocate_memory({{1, 3, 2, 3 }, data_types::f16, format::bfyx});

    topology topology(input_layout("input0", input0->get_layout()),
                      input_layout("input1", input1->get_layout()),
                      input_layout("input2", input2->get_layout()),
                      input_layout("input3", input3->get_layout()),
                      input_layout("input4", input4->get_layout()),
                      input_layout("input5", input5->get_layout()),
                      data("weights1", weights1),
                      data("weights2", weights2),
                      concatenation("concat1",
                                    { input_info("input0"), input_info("input1"), input_info("input2") },
                                    1,
                                    data_types::f16,
                                    padding{{0, 0, 0, 0}, 0}),
                      convolution("conv1", input_info("concat1"), "weights1", "", 1, {1, 1}, {1, 1}, {0, 0}, {0, 0}, false),
                      concatenation("concat2",
                                    { input_info("input3"), input_info("input4"), input_info("input5") },
                                    1,
                                    data_types::f16,
                                    padding{{0, 0, 0, 0}, 0}),
                      convolution("conv2", input_info("concat2"), "weights2", "", 1, {1, 1}, {1, 1}, {0, 0}, {0, 0}, false),
                      eltwise("sum", {input_info("concat1"), input_info("concat2")}, eltwise_mode::sum),
                      reorder("output", input_info("sum"), {{3, 2}, data_types::f16, format::bfyx}));

    ExecutionConfig config;
    config.set_property(ov::intel_gpu::allow_new_shape_infer(true));
    auto prog = program::build_program(engine, topology, config, false, false);
    auto& cache = prog->get_kernels_cache();
    auto& conv1_node = prog->get_node("conv1");
    auto& conv2_node = prog->get_node("conv2");
    auto conv1_kernels = conv1_node.get_selected_impl()->get_kernels();
    cache.add_to_cached_kernels(conv1_kernels);
    auto conv2_kernels = conv2_node.get_selected_impl()->get_kernels();
    cache.add_to_cached_kernels(conv2_kernels);
    ASSERT_EQ(conv1_kernels.size(), conv2_kernels.size());
    for (size_t idx = 0; idx < conv1_kernels.size(); idx++) {
        auto conv1_kern = cache.get_cached_kernel_id(conv1_kernels[idx]);
        auto conv2_kern = cache.get_cached_kernel_id(conv2_kernels[idx]);
        ASSERT_EQ(conv1_kern, conv2_kern);
    }

    auto& concat1_node = prog->get_node("concat1");
    auto& concat2_node = prog->get_node("concat2");
    auto concat1_kernels = concat1_node.get_selected_impl()->get_kernels();
    cache.add_to_cached_kernels(concat1_kernels);
    auto concat2_kernels = concat2_node.get_selected_impl()->get_kernels();
    cache.add_to_cached_kernels(concat2_kernels);
    ASSERT_EQ(concat1_kernels.size(), concat2_kernels.size());
    for (size_t idx = 0; idx < concat1_kernels.size(); idx++) {
        auto concat1_kern = cache.get_cached_kernel_id(concat1_kernels[idx]);
        auto concat2_kern = cache.get_cached_kernel_id(concat2_kernels[idx]);
        ASSERT_EQ(concat1_kern, concat2_kern);
    }
}

TEST(kernels_cache, sub_kernel_ordering_test) {
    auto& engine = get_test_engine();
    ExecutionConfig config = get_test_default_config(engine);
    InferenceEngine::CPUStreamsExecutor::Config task_executor_config("sub_kernel_ordering_test", 1);
    task_executor_config._streams = 2;
    auto executor = std::make_shared<InferenceEngine::CPUStreamsExecutor>(task_executor_config);
    const size_t num_kernels = 9;
    auto _kernels_cache = std::unique_ptr<kernels_cache>(new kernels_cache(engine, config, 0, executor));
    std::vector<std::string> entry_point_list;
    std::vector<std::shared_ptr<kernel_selector::KernelString>> kernel_code_list;
    for (size_t idx = 0; idx < num_kernels; idx++) {
        std::shared_ptr<kernel_selector::KernelString> kernel_string = std::make_shared<kernel_selector::KernelString>();
        std::string entry_point = "add_kernel_" + std::to_string(idx);
        std::string kernel_code =
            R"__krnl(
                __kernel void $entry_point_name(const __global float* input0, const __global float* input1, __global float* output)
                {
                    const unsigned idx = get_global_id(0);
                    output[idx] = input0[idx] + input1[idx];

                }
            )__krnl";
        kernel_code = std::regex_replace(kernel_code, std::regex("\\$entry_point_name"), entry_point);
        kernel_string->str = kernel_code;
        kernel_string->options = "-cl-mad-enable";
        kernel_string->entry_point = entry_point;
        kernel_string->batch_compilation = true;
        entry_point_list.push_back(entry_point);
        kernel_code_list.push_back(kernel_string);
    }
    kernel_impl_params dummy_params;
    _kernels_cache->add_kernels_source(dummy_params, kernel_code_list, false);
    _kernels_cache->build_all();
    auto _out_kernels = _kernels_cache->get_kernels(dummy_params);
    ASSERT_EQ(entry_point_list.size(), _out_kernels.size());
    for (size_t i = 0; i < entry_point_list.size(); i++) {
        ASSERT_EQ(entry_point_list[i], _out_kernels[i]->get_id());
    }
}
