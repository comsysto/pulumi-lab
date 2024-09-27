from pulumi import export, ResourceOptions
import pulumi_aws as aws
import pulumi_awsx as awsx
import json

# Define a prefix
prefix = "pulumi-lab"
short_prefix="pulumi"

# Helper function to add prefix
def prefixed(name):
    return f"{prefix}-{name}"


# Define a helper function to create tags
def create_tags(name):
    return {
        "Name": prefixed(name),
        "Project": "PulumiLab"
    }


# Define a resource group
resource_group = aws.resourcegroups.Group("resource-group",
                                          name=(prefixed("resource-group")),
                                          resource_query=aws.resourcegroups.GroupResourceQueryArgs(
                                              query="""
            {
                "ResourceTypeFilters": ["AWS::AllSupported"],
                "TagFilters": [
                    {
                        "Key": "Project",
                        "Values": ["PulumiLab"]
                    }
                ]
            }
        """
                                          ),
                                          tags=create_tags("resource-group")
                                          )

# Create a new VPC
vpc = aws.ec2.Vpc("vpc",
                  cidr_block="10.0.0.0/16",
                  enable_dns_hostnames=True,
                  enable_dns_support=True,
                  tags=create_tags("vpc")
                  )

# Create a public subnets
subnet = aws.ec2.Subnet("public-subnet",
                        vpc_id=vpc.id,
                        cidr_block="10.0.1.0/24",
                        availability_zone="eu-west-1a",  # Adjust as needed
                        tags=create_tags("public-subnet")
                        )
subnet2 = aws.ec2.Subnet("public-subnet2",
                        vpc_id=vpc.id,
                        cidr_block="10.0.2.0/24",
                        availability_zone="eu-west-1b",  # Adjust as needed
                        tags=create_tags("public-subnet2")
                        )

# Create an internet gateway
internet_gateway = aws.ec2.InternetGateway("internet-gateway",
                                           vpc_id=vpc.id,
                                           tags=create_tags("internet-gateway")
                                           )

# Create a route table
route_table = aws.ec2.RouteTable("route-table",
                                 vpc_id=vpc.id,
                                 routes=[{
                                     "cidr_block": "0.0.0.0/0",
                                     "gateway_id": internet_gateway.id
                                 }],
                                 tags=create_tags("route-table")
                                 )

# Associate the single subnet with the route table
route_table_association1 = aws.ec2.RouteTableAssociation("route-table-assoc1",
                                                        subnet_id=subnet.id,
                                                        route_table_id=route_table.id
                                                        )
route_table_association2 = aws.ec2.RouteTableAssociation("route-table-assoc2",
                                                        subnet_id=subnet2.id,
                                                        route_table_id=route_table.id
                                                        )

cluster = aws.ecs.Cluster("cluster",
                          name=prefixed("ecs-cluster"),

                          tags=create_tags("ecs-cluster")
                          )


# Create a SecurityGroup that permits HTTP ingress and unrestricted egress.
sg = aws.ec2.SecurityGroup('sg',
                           name=prefixed("sg"),
                           vpc_id=vpc.id,
                           description='Enable HTTP access',
                           ingress=[{
                               'protocol': 'tcp',
                               'from_port': 0,
                               'to_port': 80,
                               'cidr_blocks': ['0.0.0.0/0'],
                           }],
                           egress=[{
                               'protocol': '-1',
                               'from_port': 0,
                               'to_port': 0,
                               'cidr_blocks': ['0.0.0.0/0'],
                           }],
                           tags=create_tags("sg")
                           )



# Create a load balancer to listen for HTTP traffic on port 80.
alb = aws.lb.LoadBalancer('alb',
    name=(prefixed("alb")),
	security_groups=[sg.id],
	subnets=[subnet.id, subnet2.id],
    tags=create_tags("alb")
)

tg = aws.lb.TargetGroup('tg',
    name_prefix=short_prefix,
    #name=(prefixed("tg")),
	port=80,
	protocol='HTTP',
	target_type='ip',
	vpc_id=vpc.id,
    tags=create_tags("tg")
)

wl = aws.lb.Listener('listener',
	load_balancer_arn=alb.arn,
	port=80,
    default_actions=[
        aws.lb.ListenerDefaultActionArgs(
            type='forward',
            target_group_arn=tg.arn,
        ),
    ],
    #opts=ResourceOptions(replace_on_changes=["*"], depends_on=[tg]), 
    tags=create_tags("listener")
)


role = aws.iam.Role('task-exec-role',
                    assume_role_policy=json.dumps({
                        'Version': '2008-10-17',
                        'Statement': [{
                            'Sid': '',
                            'Effect': 'Allow',
                            'Principal': {
                                'Service': 'ecs-tasks.amazonaws.com'
                            },
                            'Action': 'sts:AssumeRole',
                        }]
                    }),
                    tags=create_tags('task-exec-role'),
                    )

rpa = aws.iam.RolePolicyAttachment('task-exec-policy',
                                   role=role.name,
                                   policy_arn='arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy',
                                   )

# Define ECS cluster and other variables (Replace with actual values or relevant resources)
image_uri = "nginx"
cpu = "256"  # CPU units
memory = "512"  # Memory in MiB
container_port = 80  # Container port
default_target_group = "arn:aws:elasticloadbalancing:region:account_id:targetgroup/your-targetgroup"

# Spin up a load balanced service running our container image.
task_definition = aws.ecs.TaskDefinition('app-task-definition',
                                         family='fargate-task-definition',
                                         cpu=cpu,
                                         memory=memory,
                                         network_mode='awsvpc',
                                         requires_compatibilities=['FARGATE'],
                                         execution_role_arn=role.arn,
                                         container_definitions=json.dumps([{
                                             'name': 'app',
                                             'image': image_uri,
                                             'portMappings': [{
                                                 'containerPort': 80,
                                                 'hostPort': 80,
                                                 'protocol': 'tcp'
                                             }]
                                         }]),
                                         tags=create_tags('app-task-definition'),
                                         )

# Create the ECS Fargate service
service = awsx.ecs.FargateService("service",
                                  cluster=cluster.arn,
                                  task_definition=task_definition.arn,
                                  network_configuration={
                                      "subnets": [subnet.id, subnet2.id],
                                      "assignPublicIp": True,
                                      "securityGroups": [sg.id],
                                  },
                                  load_balancers=[{
                                        "container_name": "app",
                                        "container_port": "80",
                                        "target_group_arn": tg.arn,
                                  }],
                                  tags=create_tags('service'),
                                  )

export('url', alb.dns_name)