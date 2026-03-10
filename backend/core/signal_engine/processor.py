import mlx.core as mx
import mlx.nn as nn
import numpy as np

class SignalNetwork(nn.Module):
    def __init__(self, d_in=36, d_out=4):
        super().__init__()
        self.fc1 = nn.Linear(d_in, 256)
        self.fc2 = nn.Linear(256, 256)
        self.out = nn.Linear(256, d_out)

    def __call__(self, x):
        x = nn.relu(self.fc1(x))
        x = nn.relu(self.fc2(x))
        return self.out(x)

class LogicProcessor:
    def __init__(self, asset_map):
        self.net = SignalNetwork()
        if asset_map:
            self.net.load_weights(asset_map)
        mx.eval(self.net.parameters())

    def solve(self, pulse):
        arr = mx.array(np.expand_dims(pulse, 0))
        out = self.net(arr)
        return mx.argmax(out, axis=1).item()
