import torch as th


class Transform:
    def transform(self, tensor):
        raise NotImplementedError

    def infer_output_info(self, vshape_in, dtype_in):
        raise NotImplementedError


class OneHot(Transform):
    def __init__(self, out_dim):
        self.out_dim = out_dim

    def transform(self, tensor):
        y_onehot = tensor.new(*tensor.shape[:-1], self.out_dim).zero_()
        y_onehot.scatter_(-1, tensor.long(), 1)
        return y_onehot.float()

    def infer_output_info(self, vshape_in, dtype_in):
        return (self.out_dim,), th.float32


class MultiDiscreteOneHot(Transform):
    def __init__(self, out_dims):
        self.out_dims = [int(x) for x in out_dims]
        self.out_dim = sum(self.out_dims)

    def transform(self, tensor):
        parts = []
        for idx, dim in enumerate(self.out_dims):
            values = tensor[..., idx:idx + 1].long()
            y_onehot = tensor.new(*tensor.shape[:-1], dim).zero_()
            y_onehot.scatter_(-1, values, 1)
            parts.append(y_onehot.float())
        return th.cat(parts, dim=-1)

    def infer_output_info(self, vshape_in, dtype_in):
        return (self.out_dim,), th.float32
