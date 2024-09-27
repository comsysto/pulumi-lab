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

# Resource names
resource_group_name = prefixed("resource-group")
vpc_name = prefixed("vpc")
public_subnet1_name = prefixed("public-subnet1")
public_subnet2_name = prefixed("public-subnet2")
internet_gateway_name = prefixed("internet-gateway")
route_table_name = prefixed("route-table")
route_table_association1_name = prefixed("route-table-assoc1")
route_table_association2_name = prefixed("route-table-assoc2")
ecs_cluster_name = prefixed("ecs-cluster")
sg_name = prefixed("sg")
alb_name = prefixed("alb")
tg_name = prefixed("tg")
wl_name = prefixed("listener")
role_name = prefixed("task-exec-role")
rpa_name = prefixed("task-exec-policy")
task_definition_name = prefixed("app-task-definition")
service_name = prefixed("service")



# Define a helper function to create tags
def create_tags(name):
    return {
        "Name": name,
        "Project": "PulumiLab"
    }


# Define a resource group
resource_group = aws.resourcegroups.Group(resource_group_name,
                                          name=resource_group_name,
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
                                          tags=create_tags(resource_group_name)
                                          )

# Create a new VPC
vpc = aws.ec2.Vpc(vpc_name,
                  cidr_block="10.0.0.0/16",
                  enable_dns_hostnames=True,
                  enable_dns_support=True,
                  tags=create_tags(vpc_name)
                  )

# Create a public subnets
subnet1 = aws.ec2.Subnet(public_subnet1_name,
                        vpc_id=vpc.id,
                        cidr_block="10.0.1.0/24",
                        availability_zone="eu-west-1a",  # Adjust as needed
                        tags=create_tags(public_subnet1_name)
                        )
subnet2 = aws.ec2.Subnet(public_subnet2_name,
                        vpc_id=vpc.id,
                        cidr_block="10.0.2.0/24",
                        availability_zone="eu-west-1b",  # Adjust as needed
                        tags=create_tags(public_subnet2_name)
                        )

# Create an internet gateway
internet_gateway = aws.ec2.InternetGateway(internet_gateway_name,
                                           vpc_id=vpc.id,
                                           tags=create_tags(internet_gateway_name)
                                           )

# Create a route table
route_table = aws.ec2.RouteTable(route_table_name,
                                 vpc_id=vpc.id,
                                 routes=[{
                                     "cidr_block": "0.0.0.0/0",
                                     "gateway_id": internet_gateway.id
                                 }],
                                 tags=create_tags(route_table_name)
                                 )

# Associate the single subnet with the route table
route_table_association1 = aws.ec2.RouteTableAssociation(route_table_association1_name,
                                                        subnet_id=subnet1.id,
                                                        route_table_id=route_table.id
                                                        )
route_table_association2 = aws.ec2.RouteTableAssociation(route_table_association2_name,
                                                        subnet_id=subnet2.id,
                                                        route_table_id=route_table.id
                                                        )

cluster = aws.ecs.Cluster(ecs_cluster_name,
                          name=ecs_cluster_name,

                          tags=create_tags(ecs_cluster_name)
                          )


# Create a SecurityGroup that permits HTTP ingress and unrestricted egress.
sg = aws.ec2.SecurityGroup(sg_name,
                           name=sg_name,
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
                           tags=create_tags(sg_name)
                           )



# Create a load balancer to listen for HTTP traffic on port 80.
alb = aws.lb.LoadBalancer(alb_name,
    name=alb_name,
	security_groups=[sg.id],
	subnets=[subnet1.id, subnet2.id],
    tags=create_tags(alb_name)
)

tg = aws.lb.TargetGroup(tg_name,
    name_prefix=short_prefix,
    #name=tg_name,
	port=80,
	protocol='HTTP',
	target_type='ip',
	vpc_id=vpc.id,
    tags=create_tags(tg_name)
)

wl = aws.lb.Listener(wl_name,
	load_balancer_arn=alb.arn,
	port=80,
    default_actions=[
        aws.lb.ListenerDefaultActionArgs(
            type='forward',
            target_group_arn=tg.arn,
        ),
    ],
    #opts=ResourceOptions(replace_on_changes=["*"], depends_on=[tg]), 
    tags=create_tags(wl_name)
)


role = aws.iam.Role(role_name,
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
                    tags=create_tags(role_name),
                    )

rpa = aws.iam.RolePolicyAttachment(rpa_name,
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
task_definition = aws.ecs.TaskDefinition(task_definition_name,
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
                                         tags=create_tags(task_definition_name),
                                         )


# Create the ECS Fargate service
service = awsx.ecs.FargateService(service_name,
                                  cluster=cluster.arn,
                                  task_definition=task_definition.arn,
                                  network_configuration={
                                      "subnets": [subnet1.id, subnet2.id],
                                      "assignPublicIp": True,
                                      "securityGroups": [sg.id],
                                  },
                                  load_balancers=[{
                                        "container_name": "app",
                                        "container_port": "80",
                                        "target_group_arn": tg.arn,
                                  }],
                                  tags=create_tags(service_name),
                                  )


export('url', alb.dns_name)