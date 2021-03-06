#   Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import

import numpy as np
import math
import collections
from paddle2onnx.constant import dtypes
from paddle2onnx.op_mapper import OpMapper as op_mapper
from paddle2onnx.op_mapper import mapper_helper


@op_mapper(['conv2d', 'depthwise_conv2d'])
class Conv():
    support_opset_verison_range = (1, 12)

    @classmethod
    def opset_1(cls, graph, node, **kw):
        kernel_shape = node.input_shape('Filter', 0)
        dilations = node.attr('dilations')
        kernel_shape = kernel_shape[-2:]
        strides = node.attr('strides')
        group = node.attr('groups')
        pads = node.attr('paddings') + node.attr('paddings')
        attrs = {
            'dilations': dilations,
            'kernel_shape': kernel_shape,
            'strides': strides,
            'group': group
        }
        auto_pad = node.attr('padding_algorithm')
        if auto_pad == 'SAME':
            attrs['auto_pad'] = 'SAME_UPPER'
        elif auto_pad == 'VALID':
            attrs['auto_pad'] = 'VALID'
        else:
            attrs['pads'] = pads
        graph.make_node(
            'Conv',
            inputs=node.input('Input') + node.input('Filter'),
            outputs=node.output('Output'),
            attrs=attrs)


@op_mapper('conv2d_transpose')
class ConvTranspose():
    support_opset_verison_range = (1, 12)

    @classmethod
    def opset_1(cls, graph, node, **kw):
        kernel_shape = node.input_shape('Filter', 0)
        node = graph.make_node(
            'ConvTranspose',
            inputs=node.input('Input') + node.input('Filter'),
            outputs=node.output('Output'),
            dilations=node.attr('dilations'),
            kernel_shape=kernel_shape[-2:],
            strides=node.attr('strides'),
            group=1,
            pads=node.attr('paddings') + node.attr('paddings'))


@op_mapper('pool2d')
class Pool():
    support_opset_verison_range = (1, 12)
    pool_type = {
        'max': ('MaxPool', 'GlobalMaxPool'),
        'avg': ('AveragePool', 'GlobalAveragePool')
    }

    @classmethod
    def is_same_span(cls, in_size, out_size):
        spans = []
        for i in range(out_size):
            start = math.floor(i * (in_size / out_size))
            end = math.ceil((i + 1) * (in_size / out_size))
            spans.append(end - start)
        if len(set(spans)) == 1:
            return True
        print(spans)
        return False

    @classmethod
    def opset_1(cls, graph, node, **kw):
        if node.attr('global_pooling'):
            onnx_node = graph.make_node(
                cls.pool_type[node.attr('pooling_type')][1],
                inputs=node.input('X'),
                outputs=node.output('Out'))
        elif node.attr('adaptive'):
            input_h, input_w = node.input_shape('X', 0)[2:]
            output_h, output_w = node.output_shape('Out', 0)[2:]
            stride_h = int(input_h / output_h)
            stride_w = int(input_w / output_w)
            kernel_h = input_h - (output_h - 1) * stride_h
            kernel_w = input_w - (output_w - 1) * stride_w

            if not cls.is_same_span(input_h, output_h) or not cls.is_same_span(
                    input_w, output_w):
                raise Exception(
                    "Cannot convert adaptive pool with input_size: {}, output_size: {}".
                    format(
                        node.input_shape('X', 0), node.output_shape('Out', 0)))
            else:
                attrs = {
                    'kernel_shape': (kernel_h, kernel_w),
                    'strides': (stride_h, stride_w),
                }
                if node.attr('ceil_mode') and graph.opset_version < 10:
                    raise Exception(
                        "Cannot convert pool with ceil_model == True to ONNX Opset version < 10, }"
                    )
                elif graph.opset_version > 10:
                    attrs['ceil_mode'] = node.attr('ceil_mode')
                auto_pad = node.attr('padding_algorithm')
                if auto_pad == 'SAME':
                    attrs['auto_pad'] = 'SAME_UPPER'
                elif auto_pad == 'VALID':
                    attrs['auto_pad'] = 'VALID'
                if node.attr('pooling_type') == 'avg':
                    attrs['count_include_pad'] = not node.attr('exclusive')
                onnx_node = graph.make_node(
                    cls.pool_type[node.attr('pooling_type')][0],
                    inputs=node.input('X'),
                    outputs=node.output('Out'),
                    attrs=attrs)
        else:
            input_shape = node.input_shape('X', 0)
            k_size = node.attr('ksize')
            paddings = node.attr('paddings')
            if input_shape[2] > 0 and input_shape[2] + paddings[0] < k_size[0]:
                k_size[0] = input_shape[2] + paddings[0]
            if input_shape[3] > 0 and input_shape[3] + paddings[1] < k_size[1]:
                k_size[1] = input_shape[3] + paddings[1]
            attrs = {
                'kernel_shape': k_size,
                'strides': node.attr('strides'),
                'pads': node.attr('paddings') + node.attr('paddings'),
            }
            if node.attr('ceil_mode') and graph.opset_version < 10:
                raise Exception(
                    "Cannot convert pool with ceil_model == True to ONNX Opset version < 10, }"
                )
            elif graph.opset_version > 10:
                attrs['ceil_mode'] = node.attr('ceil_mode')

            if node.attr('pooling_type') == 'avg':
                attrs['count_include_pad'] = not node.attr('exclusive')
            onnx_node = graph.make_node(
                cls.pool_type[node.attr('pooling_type')][0],
                inputs=node.input('X'),
                outputs=node.output('Out'),
                attrs=attrs)


@op_mapper('norm')
class Norm():
    support_opset_verison_range = (1, 12)

    @classmethod
    def opset_1(cls, graph, node, **kw):
        node = graph.make_node(
            'LpNormalization',
            inputs=node.input('X'),
            outputs=node.output('Out'),
            axis=node.attr('axis'))


@op_mapper('layer_norm')
class LayerNorm():
    support_opset_verison_range = (9, 12)

    @classmethod
    def opset_9(cls, graph, node, **kw):
        ipt = node.input('X', 0)
        ipt_dims = len(node.input_shape('X', 0))
        normalized_shape = node.attr('begin_norm_axis')
        if isinstance(normalized_shape, collections.Iterable):
            axes = [-i for i in range(len(normalized_shape), 0, -1)]
        else:
            axes = [i for i in range(normalized_shape, ipt_dims)]

        epsilon = graph.make_node(
            'Constant', dtype=dtypes.ONNX.FLOAT, value=node.attr('epsilon'))
        two = graph.make_node('Constant', dtype=dtypes.ONNX.FLOAT, value=2.0)
        mean = graph.make_node("ReduceMean", inputs=[ipt], axes=axes)
        numerator = graph.make_node("Sub", inputs=[ipt, mean])
        pow_num = graph.make_node("Pow", inputs=[numerator, two])
        variance = graph.make_node("ReduceMean", inputs=[pow_num], axes=axes)
        add_eps = graph.make_node("Add", inputs=[variance, epsilon])
        denominator = graph.make_node("Sqrt", inputs=[add_eps])

        if 'Bias' in node.inputs and 'Scale' in node.inputs:
            ipt_shape = graph.make_node("Shape", inputs=[ipt])
            weight_shape = mapper_helper.slice_helper(
                graph, ipt_shape, [0], [ipt_dims - len(axes)], [ipt_dims])
            scale = graph.make_node(
                "Reshape", inputs=[node.input('Scale', 0), weight_shape])
            bias = graph.make_node(
                "Reshape", inputs=[node.input('Bias', 0), weight_shape])
            layer_norm = graph.make_node("Div", inputs=[numerator, denominator])
            layer_norm = graph.make_node("Mul", inputs=[layer_norm, scale])
            graph.make_node(
                "Add", inputs=[layer_norm, bias], outputs=node.output('Y'))
        elif 'Bias' in node.inputs:
            ipt_shape = graph.make_node("Shape", inputs=[ipt])
            weight_shape = mapper_helper.slice_helper(
                graph, ipt_shape, [0], [ipt_dims - len(axes)], [ipt_dims])
            bias = graph.make_node(
                "Reshape", inputs=[node.input('Bias', 0), weight_shape])
            layer_norm = graph.make_node("Div", inputs=[numerator, denominator])
            graph.make_node(
                "Add", inputs=[layer_norm, bias], outputs=node.output('Y'))
        elif 'Scale' in node.inputs:
            ipt_shape = graph.make_node("Shape", inputs=[ipt])
            weight_shape = mapper_helper.slice_helper(
                graph, ipt_shape, [0], [ipt_dims - len(axes)], [ipt_dims])
            scale = graph.make_node(
                "Reshape", inputs=[node.input('Scale', 0), weight_shape])
            layer_norm = graph.make_node("Div", inputs=[numerator, denominator])
            graph.make_node(
                "Mul", inputs=[layer_norm, scale], outputs=node.output('Y'))
        else:
            layer_norm = graph.make_node(
                "Div",
                inputs=[numerator, denominator],
                outputs=node.output('Y'))


@op_mapper('batch_norm')
class BatchNorm():
    support_opset_verison_range = (1, 12)

    @classmethod
    def make_attrs_and_inputs(cls, graph, node, **kw):
        onnx_attr = {
            'epsilon': node.attr('epsilon'),
            'momentum': node.attr('momentum')
        }
        inputs = node.input('X') + node.input('Scale') + node.input(
            'Bias') + node.input('Mean') + node.input('Variance')
        return onnx_attr, inputs

    @classmethod
    def opset_9(cls, graph, node, **kw):
        onnx_attr, inputs = cls.make_attrs_and_inputs(graph, node, **kw)
        onnx_node = graph.make_node(
            'BatchNormalization',
            inputs=inputs,
            outputs=node.output('Y'),
            **onnx_attr)

    @classmethod
    def opset_7(cls, graph, node, **kw):
        onnx_attr, inputs = cls.make_attrs_and_inputs(graph, node, **kw)
        onnx_attr['spatial'] = 0
        onnx_node = graph.make_node(
            'BatchNormalization',
            inputs=inputs,
            outputs=node.output('Y'),
            **onnx_attr)

    @classmethod
    def opset_1(cls, graph, node, **kw):
        onnx_attr, inputs = cls.make_attrs_and_inputs(graph, node, **kw)
        onnx_attr['is_test'] = 1
        onnx_node = graph.make_node(
            'BatchNormalization',
            inputs=inputs,
            outputs=node.output('Y'),
            **onnx_attr)


@op_mapper('instance_norm')
class InstanceNorm():
    support_opset_verison_range = (1, 12)

    @classmethod
    def opset_1(cls, graph, node, **kw):
        onnx_attr = {'epsilon': node.attr('epsilon'), }
        inputs = node.input('X') + node.input('Scale') + node.input('Bias')
        onnx_node = graph.make_node(
            'InstanceNormalization',
            inputs=inputs,
            outputs=node.output('Y'),
            **onnx_attr)


@op_mapper('dropout')
class Dropout():
    support_opset_verison_range = (7, 12)

    @classmethod
    def opset_7(cls, graph, node, **kw):
        dropout_mode = node.attr('dropout_implementation')
        dropout_prob = node.attr('dropout_prob')
        if dropout_mode == 'upscale_in_train':
            onnx_node = graph.make_node(
                'Identity', inputs=node.input('X'), outputs=node.output('Out'))
        elif dropout_mode == 'downgrade_in_infer':
            scale_node = graph.make_node(
                'Constant',
                attrs={'dtype': dtypes.ONNX.FLOAT,
                       'value': 1 - dropout_prob})
            graph.make_node(
                "Mul",
                inputs=[node.input('X')[0], scale_node],
                outputs=node.output('Out'))
        else:
            raise Exception("Unexpected situation happend")


@op_mapper('roi_align')
class RoiAlign():
    support_opset_verison_range = (10, 12)

    @classmethod
    def opset_10(cls, graph, node, **kw):
        rois_shape = graph.make_node('Shape', inputs=[node.input('ROIs', 0)])
        starts = graph.make_node(
            'Constant', attrs={'dtype': dtypes.ONNX.INT64,
                               'value': [0]})
        ends = graph.make_node(
            'Constant', attrs={'dtype': dtypes.ONNX.INT64,
                               'value': [1]})
        num_rois = graph.make_node('Slice', inputs=[rois_shape, starts, ends])
        zero = graph.make_node(
            'Constant', dims=[1], dtype=dtypes.ONNX.INT64, value=[0])
        batch_indices = graph.make_node('Expand', inputs=[zero, num_rois])
        node = graph.make_node(
            'RoiAlign',
            inputs=[node.input('X', 0), node.input('ROIs', 0), batch_indices],
            outputs=node.output('Out'),
            mode='avg',
            output_height=node.attr('pooled_height'),
            output_width=node.attr('pooled_width'),
            sampling_ratio=node.attr('sampling_ratio'),
            spatial_scale=node.attr('spatial_scale'))
