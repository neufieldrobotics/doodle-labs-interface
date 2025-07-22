from setuptools import find_packages, setup

package_name = 'doodle_monitor'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/doodle_monitor.launch.py']),
        ('share/' + package_name + '/config', ['config/network_params.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='neuroam',
    maintainer_email='neuroam@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'monitor_node = doodle_monitor.monitor_node:main',
            'optimized_payload_monitor = doodle_monitor.optimized_payload_monitor:main',
            'iperf_server_node = doodle_monitor.iperf_server_node:main',
            'graph_visualizer = doodle_monitor.graph_visualizer:main',
        ],
    },
)
