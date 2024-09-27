import pulumi 
import pulumi_aws as aws
import pulumi_awsx as awsx
import json

# Variables
config = pulumi.Config()

region = config.require("region")
az_number = config.require_int("az_number")
prefix = config.require("prefix")
short_prefix = config.require("short_prefix")
image_uri = config.require("image_uri")
cpu = config.require("cpu")
memory = config.require("memory")
container_port = config.require_int("container_port")


# Functions
def prefixed(name):
    return f"{prefix}-{name}"

def create_tags(name):
    return {
        "Name": name,
        "Project": "PulumiLab"
    }


# Resources
resource_group_name = prefixed("resource-group")
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


vpc_name = prefixed("vpc")
vpc = aws.ec2.Vpc(vpc_name,
                  cidr_block="10.0.0.0/16",
                  enable_dns_hostnames=True,
                  enable_dns_support=True,
                  tags=create_tags(vpc_name)
                  )


internet_gateway_name = prefixed("internet-gateway")
internet_gateway = aws.ec2.InternetGateway(internet_gateway_name,
                                           vpc_id=vpc.id,
                                           tags=create_tags(internet_gateway_name)
                                           )


public_route_table_name = prefixed("public-route-table")
public_route_table = aws.ec2.RouteTable(public_route_table_name,
                                 vpc_id=vpc.id,
                                 routes=[{
                                     "cidr_block": "0.0.0.0/0",
                                     "gateway_id": internet_gateway.id
                                 }],
                                 tags=create_tags(public_route_table_name)
                                 )


public_subnets_ids = []
private_subnets_ids = []

for i in range(az_number):

    public_subnet_name=f"{prefixed("public-subnet")}-{i}"
    public_subnet = aws.ec2.Subnet(
        public_subnet_name, 
        vpc_id=vpc.id, 
        cidr_block=f"10.0.{i+1}.0/24", 
        availability_zone=f"{region}{chr(97+i)}",
        map_public_ip_on_launch=True,
        tags=create_tags(public_subnet_name)
    )
    public_subnets_ids.append(public_subnet.id)


    public_route_table_assoc_name=f"{prefixed("public-route-table-assoc")}-{i}"
    public_route_table_assoc = aws.ec2.RouteTableAssociation(public_route_table_assoc_name,
                                                            subnet_id=public_subnet.id,
                                                            route_table_id=public_route_table.id
                                                            )


    private_subnet_name=f"{prefixed("private-subnet")}-{i}"
    private_subnet = aws.ec2.Subnet(
        private_subnet_name, 
        vpc_id=vpc.id, 
        cidr_block=f"10.0.{i+4}.0/24", 
        availability_zone=f"{region}{chr(97+i)}",
        map_public_ip_on_launch=False,
        tags=create_tags(private_subnet_name)
    )
    private_subnets_ids.append(private_subnet.id)


    eip_name=f"{prefixed("eip")}-{i}"
    eip = aws.ec2.Eip(eip_name,
        tags=create_tags(eip_name)
    )


    nat_gw_name=f"{prefixed("nat-gw")}-{i}"
    nat_gateway = aws.ec2.NatGateway(nat_gw_name,
        subnet_id=public_subnet.id,
        allocation_id=eip.allocation_id,
        tags=create_tags(nat_gw_name)
    )


    private_route_table_name=f"{prefixed("private-route-table")}-{i}"
    private_route_table = aws.ec2.RouteTable(private_route_table_name,
        vpc_id=vpc.id,
        routes=[{
            "cidr_block": "0.0.0.0/0",
            "gateway_id": nat_gateway.id
        }],
        tags=create_tags(private_route_table_name)
    )


    private_route_table_assoc_name=f"{prefixed("private-route-table-assoc")}-{i}"
    private_route_table_assoc = aws.ec2.RouteTableAssociation(private_route_table_assoc_name,
                                                            subnet_id=private_subnet.id,
                                                            route_table_id=private_route_table.id
                                                            )


ecs_cluster_name = prefixed("ecs-cluster")
cluster = aws.ecs.Cluster(ecs_cluster_name,
                          name=ecs_cluster_name,

                          tags=create_tags(ecs_cluster_name)
                          )


sg_name = prefixed("sg")
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


alb_name = prefixed("alb")
alb = aws.lb.LoadBalancer(alb_name,
    name=alb_name,
	security_groups=[sg.id],
	subnets=public_subnets_ids,
    tags=create_tags(alb_name)
)


tg_name = prefixed("tg")
tg = aws.lb.TargetGroup(tg_name,
    name_prefix=short_prefix,
	port=80,
	protocol='HTTP',
	target_type='ip',
	vpc_id=vpc.id,
    tags=create_tags(tg_name)
)


listener_name = prefixed("listener")
listener = aws.lb.Listener(listener_name,
	load_balancer_arn=alb.arn,
	port=80,
    default_actions=[
        aws.lb.ListenerDefaultActionArgs(
            type='forward',
            target_group_arn=tg.arn,
        ),
    ],
    tags=create_tags(listener_name)
)


role_name = prefixed("task-exec-role")
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


rpa_name = prefixed("task-exec-policy")
rpa = aws.iam.RolePolicyAttachment(rpa_name,
                                   role=role.name,
                                   policy_arn='arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy',
                                   )


task_definition_name = prefixed("app-task-definition")
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


service_name = prefixed("service")
service = awsx.ecs.FargateService(service_name,
                                  cluster=cluster.arn,
                                  task_definition=task_definition.arn,
                                  network_configuration={
                                      "subnets": private_subnets_ids,
                                      "assignPublicIp": False,
                                      "securityGroups": [sg.id],
                                  },
                                  load_balancers=[{
                                        "container_name": "app",
                                        "container_port": "80",
                                        "target_group_arn": tg.arn,
                                  }],
                                  tags=create_tags(service_name),
                                  )

# Outputs
pulumi.export('url', alb.dns_name)
