bl_info = {
	"name": "WTool",
	"author": "WTom",
	"version": (0, 0, 5),
	"blender": (2, 80, 0),
	"location": "View3D > Object Tools",
	"description": "Create primitives at origins or vertices",
	"category": "Object"}
	

import bpy
import bmesh
import mathutils
from mathutils import Vector,Matrix,Euler
from math import radians
import gpu
from gpu_extras.batch import batch_for_shader
import bgl

max_clonedObjects = 5000

bpy.types.Scene.target = bpy.props.PointerProperty(type=bpy.types.Object)
bpy.types.Scene.alignto = bpy.props.PointerProperty(type=bpy.types.Object)


averageNormals = Vector((0,0,0))
n__sum = 0
align_hidden=False
gizmo_visible=False
marked3dCursor_pos = []
cloned_objs = []
mod_self = False

dns = bpy.app.driver_namespace
handle = dns.get("dc")


def RefreshGizmo(self, context):
	global gizmo_visible
	if gizmo_visible:
		dm = DrawGizmo(context.scene.target.location)
		dm.stopDraw()
		dm.draw()
		dm.doDraw()	
		context.area.tag_redraw()
	

class Wtool_Properties(bpy.types.PropertyGroup):	
			
	IS_IndVOrigin:bpy.props.BoolProperty(
			name = "Set Individual Origins", 
			description = "Apply Geometry to Origin on every selected object",
			default = False)
			
	IS_Norm:bpy.props.BoolProperty(
			name = "Normals as Rotation(Selected)", 
			description = "Changes the Cloned object Rotation to match the Selected object vertex normal",
			default = True)
			
	IS_AVG:bpy.props.BoolProperty(
			name = "Avarage Normals", 
			description = "Avarage used normals",
			default = False)
			
	AVGNormal_Range:bpy.props.IntProperty(
			name = "Get Closest Normals", 
			description = "This will get the Normals on Aligned Object that is closest to the selected object vertex and avarage them out",
			min=1, 
			max=50,
			default = 4)
					
	AlignOption : bpy.props.EnumProperty(
		name="",
		description="Align to options",
		items=[
			('OP1',"Closest Face","Closest Face to Selected Object Vertex"),
			('OP2',"Closest Vertex","Closest Vertex to Selected Object Vertex"),
			('OP3',"Both","Closest Face or/and Vertex to Selected Object Vertex"),
			('OP4',"Origin","Project a Normal from Origin to the direction of Selected Object Vertex"),
			('OP5',"3D Cursor","Project a Normal from 3D Cursor location to the direction of Selected Object Vertex")
		],
		default = 'OP3'
	)	
	
	ViewDirection : bpy.props.EnumProperty(
		name="View Direction",
		description="Converts World to Local direction",
		items=[
			('OP1',"+z",""),
			('OP2',"-z",""),
			('OP3',"+x",""),
			('OP4',"-x",""),
			('OP5',"+y",""),
			('OP6',"-y",""),
		],
		default = 'OP5',
		update = RefreshGizmo
	)	
	
	PlaceOptions : bpy.props.EnumProperty(
		name="Place at",
		description="Place Cloned Objects on:",
		items=[
			('OP1',"Origin",""),
			('OP2',"Vertex",""),
			('OP3',"Face",""),
			('OP4',"3d Cursor",""),
		],
		default = 'OP2'
	)	
	
	IS_NormInverted:bpy.props.BoolProperty(
			name = "Invert Normal Rotation", 
			description = "Changes Object rotation by 180",
			default = False)
			

	IS_JoinObjects:bpy.props.BoolProperty(
			name = "Join Objects", 
			description = "Joins Cloned Objects to Single Object after Use was clicked",
			default = False)
			
	IS_AutoSync:bpy.props.BoolProperty(
			name = "Auto Sync Clones", 
			description = "Automatically synchronizes the cloned objects data, transformation, materials, modifiers from the original  targeted object",
			default = True)
			

def message_draw(self, context):
	
	global groupname
	
	layout = self.layout
	row = layout.row()
	row.label(text = message)


def SyncMeshes(scene):
	global mod_self, cloned_objs
	if scene.Wtool_Properties.IS_JoinObjects or not scene.Wtool_Properties.IS_AutoSync:
		return
	if mod_self:
		return
	mod_self = True
	try:
		bpy.ops.object.select_all(action='DESELECT')
		bpy.context.view_layer.objects.active = scene.target
		scene.target.select_set(True)
		bpy.ops.object.make_single_user(type='SELECTED_OBJECTS', object=True, obdata=True, material=True, animation=True)
		bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
		print(len(cloned_objs))
		for cloned_obj in cloned_objs:
			cloned_obj.select_set(True)
			cloned_obj.scale = (1, 1, 1)
		bpy.ops.object.make_links_data(type='OBDATA')
		bpy.ops.object.make_links_data(type='MODIFIERS')
		bpy.ops.object.select_all(action='DESELECT')
		scene.target.select_set(True)
	except Exception as ex:
		print(ex)
	mod_self = False



mod_counter = 0	
def selection_change_handler(scene):
	global mod_self, mod_counter
	if scene.Wtool_Properties.IS_JoinObjects or not scene.Wtool_Properties.IS_AutoSync:
		return
		
	if bpy.context.mode != "OBJECT":
		return
	depsgraph = bpy.context.evaluated_depsgraph_get()
	if selection_change_handler.operator is None:
		selection_change_handler.operator = bpy.context.active_operator 
	for update in depsgraph.updates:
		if not update.is_updated_transform and not update.is_updated_geometry:
			continue
		if selection_change_handler.operator == bpy.context.active_operator and bpy.context.active_operator.name != "Add Modifier" and bpy.context.active_operator.name != "Remove Modifier" and bpy.context.active_operator.name != "editmode_toggle":
			continue
		if bpy.context.active_operator.name == "Add Modifier" or bpy.context.active_operator.name == "Remove Modifier":
			if mod_counter > 3:
				continue
			mod_counter +=1
		elif mod_counter > 3 :
			mod_counter =0
		if not mod_self and update.id.name == scene.target.name: 
			SyncMeshes(scene)
		selection_change_handler.operator = None
	

selection_change_handler.operator = None

		
class PANEL_PT_WTool(bpy.types.Panel):
	bl_label = "WTool"
	bl_space_type = 'VIEW_3D'
	bl_region_type = 'UI'
	bl_category = 'WTool'

	@classmethod
	def poll(cls, context):
		obj = context.active_object
		return (obj and obj.type == 'MESH'  and context.mode == 'OBJECT')
		
		

	def draw(self, context):
		layout = self.layout
		scn = context.scene
		global align_hidden


		layout.operator("object.wtool", text="Use", icon = 'PLUGIN')
		layout.prop_search(context.scene, "target", context.scene, "objects", text="Clone")
		layout.prop_search(context.scene, "alignto", context.scene, "objects", text="Align Normals to(if wrapper is used)")
		layout.prop(scn.Wtool_Properties, "PlaceOptions")
		if len(bpy.context.selected_objects) > 1:
			layout.prop(scn.Wtool_Properties, "IS_IndVOrigin")
		if scn.Wtool_Properties.PlaceOptions != 'OP1':
			layout.prop(scn.Wtool_Properties, "IS_Norm")
		layout.prop(scn.Wtool_Properties, "ViewDirection")
		layout.operator("object.gizmo", text="Gizmo on Target", icon = 'GIZMO')
		if scn.alignto is not None:
			layout.prop(scn.Wtool_Properties, "IS_AVG")
		if scn.alignto is not None and scn.Wtool_Properties.IS_AVG:
			layout.prop(scn.Wtool_Properties, 'AVGNormal_Range', slider=True)
		if scn.alignto is not None:
			layout.prop(scn.Wtool_Properties, "AlignOption")
			layout.prop(scn.Wtool_Properties, "IS_NormInverted")
			align_hidden = True
		else:
			align_hidden = False
		layout.operator("object.mark", text="Save 3d Cursor", icon = 'CURSOR')
		layout.operator("object.clear", text="Clear all marked", icon = 'PANEL_CLOSE')
		layout.prop(scn.Wtool_Properties, "IS_JoinObjects")
		if not scn.Wtool_Properties.IS_JoinObjects:
			layout.prop(scn.Wtool_Properties, "IS_AutoSync")


class OBJECT_OT_WTool_Helper(bpy.types.Operator):
	bl_idname = "object.wtool"
	bl_label = "WTool"
	bl_description = "Create objects at origins,vertices"
	bl_options = {'REGISTER','UNDO'}


	
	@classmethod
	def poll(cls, context):
		obj = context.active_object
		return (obj and obj.type == 'MESH' and context.mode == 'OBJECT')
		


	def invoke(self, context, event):
		global averageNormals, n__sum, align_hidden, max_clonedObjects, cloned_objs
		v_norm=[]
		f_norm=[]
		scn = context.scene
		original_3dcurspos =  Vector(bpy.context.scene.cursor.location)
		original_3dcurs=  bpy.context.scene.cursor.matrix.decompose()
		sel_objs = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
		cloned_objs.clear()
		print(len(cloned_objs))


		if scn.target is not None:
			bpy.ops.object.select_all(action='DESELECT')
			bpy.context.view_layer.objects.active = scn.target
			scn.target.select_set(True)
			bpy.ops.object.make_single_user(type='SELECTED_OBJECTS', object=True, obdata=True)
			bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
			if len(bpy.app.handlers.depsgraph_update_post) == 0:
				bpy.app.handlers.depsgraph_update_post.append(selection_change_handler)

		if scn.alignto is not None:
			bpy.ops.object.select_all(action='DESELECT')
			bpy.context.view_layer.objects.active = scn.alignto
			scn.alignto.select_set(True)
			scn.alignto.data.calc_normals()
			bpy.ops.view3d.snap_cursor_to_selected()
			align_origin_location = Vector(bpy.context.scene.cursor.location)
			bpy.ops.object.mode_set(mode = 'EDIT')
			bpy.ops.mesh.select_all(action = 'SELECT')
			bm = bmesh.from_edit_mesh(scn.alignto.data) 
			faces = bm.faces
			size = len(bm.faces)
			facekd = mathutils.kdtree.KDTree(size)
			for i,face in enumerate(faces):
				facekd.insert(face.calc_center_median(),i)
				f_norm.append(Vector(face.normal))
			facekd.balance()
			verts = bm.verts
			size = len(bm.verts)
			vertkd = mathutils.kdtree.KDTree(size)
			for i,vert in enumerate(verts):
				vertkd.insert(vert.co,i)
				v_norm.append(Vector(vert.normal))
			vertkd.balance()
			bpy.ops.object.mode_set(mode='OBJECT')
			bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

		i=0
		for obj in sel_objs:
			bpy.ops.object.select_all(action='DESELECT')
			bpy.context.view_layer.objects.active = obj
			obj.select_set(True)

			original_pos =  Vector(bpy.context.scene.cursor.location)
			bpy.ops.view3d.snap_cursor_to_selected()
			origin_location = bpy.context.scene.cursor.location
			
			if scn.Wtool_Properties.IS_IndVOrigin:
				bpy.ops.object.mode_set(mode = 'EDIT')
				bpy.ops.mesh.select_all(action = 'SELECT')
				bpy.ops.view3d.snap_cursor_to_selected()
				bpy.ops.object.mode_set(mode='OBJECT')
				bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
			
	
			if scn.target is not None:
				C = bpy.context
				mesh = obj.data
				mesh.calc_normals_split()

				if scn.Wtool_Properties.PlaceOptions == 'OP1':
					new_obj = scn.target.copy()
					new_obj.data = scn.target.data.copy()
					new_obj.location=origin_location
					
					new_obj.rotation_euler  = obj.rotation_euler	
					v= new_obj.location
					
					if scn.alignto is not None:
						n_range = 1
						if scn.Wtool_Properties.IS_AVG:
							n_range = scn.Wtool_Properties.AVGNormal_Range

						if scn.Wtool_Properties.AlignOption == 'OP1':
							co,indx= GetClosestFaceNormals(facekd,f_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
						elif scn.Wtool_Properties.AlignOption == 'OP2':
							co,indx= GetClosestVertexNormals(vertkd,v_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
						elif scn.Wtool_Properties.AlignOption == 'OP3':
							co,indx= GetClosestFaceNormals(facekd,f_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
							co,indx2= GetClosestVertexNormals(vertkd,v_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
						elif scn.Wtool_Properties.AlignOption == 'OP4':
							co= v - align_origin_location 
							averageNormals=co
						else :
							co= v - original_3dcurspos
							averageNormals=co
							
						new_obj.matrix_world = MatrixTranslation(averageNormals,scn.alignto.matrix_world,scn.Wtool_Properties.IS_NormInverted and align_hidden,scn,context)
						new_obj.location= origin_location
						averageNormals = Vector((0,0,0))
						n__sum = 0
					
					C.collection.objects.link(new_obj)
					cloned_objs.append(new_obj)
	


				elif scn.Wtool_Properties.PlaceOptions == 'OP2':	
					for vert in mesh.vertices:
						i+=1
						if i < max_clonedObjects:
							new_obj = scn.target.copy()
							new_obj.data = scn.target.data.copy()
							v=obj.matrix_world @ vert.co
							new_obj.location= v
							

							if scn.Wtool_Properties.IS_Norm:
								new_obj.matrix_world = MatrixTranslation(vert.normal,obj.matrix_world,scn.Wtool_Properties.IS_NormInverted and align_hidden,scn,context)
								new_obj.location= v
								if scn.Wtool_Properties.IS_AVG:
									AvarageNormals(vert.normal)
							else:
								new_obj.rotation_euler  = obj.rotation_euler
							if scn.alignto is not None:
								n_range = 1
								if scn.Wtool_Properties.IS_AVG:
									n_range = scn.Wtool_Properties.AVGNormal_Range

								if scn.Wtool_Properties.AlignOption == 'OP1':
									co,indx= GetClosestFaceNormals(facekd,f_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
								elif scn.Wtool_Properties.AlignOption == 'OP2':
									co,indx= GetClosestVertexNormals(vertkd,v_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
								elif scn.Wtool_Properties.AlignOption == 'OP3':
									co,indx= GetClosestFaceNormals(facekd,f_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
									co,indx2= GetClosestVertexNormals(vertkd,v_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
								elif scn.Wtool_Properties.AlignOption == 'OP4':
									co= v - align_origin_location 
									averageNormals=co
								else :
									co= v - original_3dcurspos
									averageNormals=co
									
								new_obj.matrix_world = MatrixTranslation(averageNormals,scn.alignto.matrix_world,scn.Wtool_Properties.IS_NormInverted and align_hidden,scn,context)
								new_obj.location= v
								averageNormals = Vector((0,0,0))
								n__sum = 0
								
						C.collection.objects.link(new_obj)
						cloned_objs.append(new_obj)
				elif scn.Wtool_Properties.PlaceOptions == 'OP3':	
					for face in mesh.polygons:
						i+=1
						if i < max_clonedObjects:
							new_obj = scn.target.copy()
							new_obj.data = scn.target.data.copy()
							v=obj.matrix_world @ face.center
							new_obj.location= v
							

							if scn.Wtool_Properties.IS_Norm:
								new_obj.matrix_world = MatrixTranslation(face.normal,obj.matrix_world,scn.Wtool_Properties.IS_NormInverted and align_hidden,scn,context)
								new_obj.location= v
								if scn.Wtool_Properties.IS_AVG:
									AvarageNormals(face.normal)
							else:
								new_obj.rotation_euler  = obj.rotation_euler
							if scn.alignto is not None:
								n_range = 1
								if scn.Wtool_Properties.IS_AVG:
									n_range = scn.Wtool_Properties.AVGNormal_Range

								if scn.Wtool_Properties.AlignOption == 'OP1':
									co,indx= GetClosestFaceNormals(facekd,f_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
								elif scn.Wtool_Properties.AlignOption == 'OP2':
									co,indx= GetClosestVertexNormals(vertkd,v_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
								elif scn.Wtool_Properties.AlignOption == 'OP3':
									co,indx= GetClosestFaceNormals(facekd,f_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
									co,indx2= GetClosestVertexNormals(vertkd,v_norm,scn.alignto.matrix_world.inverted() @ v , n_range)
								elif scn.Wtool_Properties.AlignOption == 'OP4':
									co= v - align_origin_location 
									averageNormals=co
								else :
									co= v - original_3dcurspos
									averageNormals=co
									
								new_obj.matrix_world = MatrixTranslation(averageNormals,scn.alignto.matrix_world,scn.Wtool_Properties.IS_NormInverted and align_hidden,scn,context)
								new_obj.location= v
								averageNormals = Vector((0,0,0))
								n__sum = 0
						

						C.collection.objects.link(new_obj)
						cloned_objs.append(new_obj)
						
		
			#SyncMeshes(scn)			
		if scn.Wtool_Properties.PlaceOptions == 'OP4' and scn.target is not None:
			C = bpy.context
			
			
			if len(marked3dCursor_pos) == 0:
				new_obj = scn.target.copy()
				new_obj.data = scn.target.data.copy()
				cursor = original_3dcurs

				tc, qc, sc = cursor
				to, qo, so = new_obj.matrix_world.decompose()
				R = qc.to_matrix().to_4x4() if scn.Wtool_Properties.IS_Norm else qo.to_matrix().to_4x4()

				rot_matrix=RotationMatrix(scn,context)
	
				T = Matrix.Translation(tc) 
				T=T @ rot_matrix 
				S = Matrix.Diagonal(so).to_4x4()
				new_obj.matrix_world = T @ R @ S

		
				C.collection.objects.link(new_obj)
				cloned_objs.append(new_obj)
			else:	
				for cursor in marked3dCursor_pos:
					new_obj = scn.target.copy()
					new_obj.data = scn.target.data.copy()
					

					tc, qc, sc = cursor
					to, qo, so = new_obj.matrix_world.decompose()
					R = qc.to_matrix().to_4x4() if scn.Wtool_Properties.IS_Norm else qo.to_matrix().to_4x4()


					rot_matrix=RotationMatrix(scn,context)
		


					T = Matrix.Translation(tc) 
					T=T @ rot_matrix 
					S = Matrix.Diagonal(so).to_4x4()
					new_obj.matrix_world = T @ R @ S

			
					C.collection.objects.link(new_obj)
					cloned_objs.append(new_obj)

		bpy.context.scene.cursor.location = original_3dcurspos
		bpy.ops.object.select_all(action='DESELECT')
		bpy.context.view_layer.objects.active = scn.target
		scn.target.select_set(False)
		for cloned_obj in cloned_objs:
			cloned_obj.select_set(True)
		if scn.Wtool_Properties.IS_JoinObjects:
			bpy.context.view_layer.objects.active = cloned_objs[0]
			bpy.ops.object.join()
		
		return {'FINISHED'}
		
		
		
class OBJECT_OT_WTool_Helper2(bpy.types.Operator):
	bl_idname = "object.mark"
	bl_label = "WTool"
	bl_description = "Mark multiple 3d cursor positions for Object Placement"

	@classmethod
	def poll(cls, context):
		obj = context.active_object
		return (obj and obj.type == 'MESH' and context.mode == 'OBJECT')

	def invoke(self, context, event):
		global marked3dCursor_pos
		marked3dCursor_pos.append(bpy.context.scene.cursor.matrix.decompose())

		return {'FINISHED'}
		
		
class OBJECT_OT_WTool_Helper3(bpy.types.Operator):
	bl_idname = "object.clear"
	bl_label = "WTool"
	bl_description = "Clear all Marked 3d cursor position"
	bl_options = {'REGISTER','UNDO'}	

	@classmethod
	def poll(cls, context):
		obj = context.active_object
		return (obj and obj.type == 'MESH' and context.mode == 'OBJECT')

	def invoke(self, context, event):
		global marked3dCursor_pos
		marked3dCursor_pos = []

		return {'FINISHED'}
		
class OBJECT_OT_WTool_Helper4(bpy.types.Operator):
	bl_idname = "object.gizmo"
	bl_label = "WTool"
	bl_description = "Show/Hide Gizmo on targeted object to clone"


	@classmethod
	def poll(cls, context):
		obj = context.active_object
		return (obj and obj.type == 'MESH' and context.mode == 'OBJECT')

	def invoke(self, context, event):
		global gizmo_visible
		
		if context.scene.target is not None:
			gizmo_visible =not gizmo_visible  
			dm = DrawGizmo(context.scene.target.location)
			if gizmo_visible:
				dm.draw()
				dm.doDraw()
			else:
				dm.stopDraw()
			context.area.tag_redraw()


		return {'FINISHED'}
		
		
		
def GetClosestFaceNormals(facekd, f_norm, vert, n_inrange):
	if n_inrange > 1:
		for (co, index, dist) in facekd.find_n(vert, n_inrange): 
			co=AvarageNormals(f_norm[index])
	else:
		co, index, dist = facekd.find(vert)

	co=AvarageNormals(f_norm[index])
	return co, index
	

def GetClosestVertexNormals(vertkd, v_norm, vert, n_inrange):
	if n_inrange > 1:
		for (co, index, dist) in vertkd.find_n(vert, n_inrange): 
			co=AvarageNormals(v_norm[index])
	else:
		co, index, dist = vertkd.find(vert)
	
	co=AvarageNormals(v_norm[index])
	return co, index


def AvarageNormals(normal):
	global averageNormals, n__sum
	averageNormals = averageNormals + normal
	n__sum = n__sum + 1
	averagedNormal = averageNormals / n__sum
	return averagedNormal
	
def MatrixTranslation(co, matrixWorld, invert,scn, context):
	Sx = Matrix.Scale(-1, 4, (1, 0, 0))
	Sy = Matrix.Scale(-1, 4, (0, 1, 0))
	S = Sx @ Sy
	R = co.to_track_quat('Z', 'Y').to_matrix().to_4x4() 
	if invert:
		zrot_matrix = Euler((map(radians, (180.0, 0.0, 0.0))), 'ZYX').to_matrix().to_4x4()
		R=R @ zrot_matrix
	

	rot_matrix=RotationMatrix(scn,context)
	R=R @ rot_matrix
	R.translation = matrixWorld @ co
	return R @ S

def RotationMatrix(scn, context):

	rot_matrix = Euler((map(radians, (0.0, 0.0, 0.0))), 'ZYX').to_matrix().to_4x4()
	if scn.Wtool_Properties.ViewDirection == 'OP1':
		rot_matrix = Euler((map(radians, (-90.0, 180.0, 0.0))), 'ZYX').to_matrix().to_4x4()
	elif scn.Wtool_Properties.ViewDirection == 'OP2':
		rot_matrix = Euler((map(radians, (-90.0, 0.0, 0.0))), 'ZYX').to_matrix().to_4x4()
	elif scn.Wtool_Properties.ViewDirection == 'OP3':
		rot_matrix = Euler((map(radians, (0.0, 0.0, 90.0))), 'ZYX').to_matrix().to_4x4()
	elif scn.Wtool_Properties.ViewDirection == 'OP4':
		rot_matrix = Euler((map(radians, (180.0, 180.0, 90.0))), 'ZYX').to_matrix().to_4x4()
	elif scn.Wtool_Properties.ViewDirection == 'OP6':
		rot_matrix = Euler((map(radians, (0.0, 0.0, 180.0))), 'ZYX').to_matrix().to_4x4()

	return rot_matrix
	
	
	
class DrawGizmo:
	vertices = []
	col = []
	shader = None
	batch = None

	def __init__(self,origin):
		order = []
		order=RotationOrder(origin)
		self.vertices=[origin, order[0],origin, order[1],origin, order[2]]
		self.shader = gpu.shader.from_builtin('3D_SMOOTH_COLOR')
		self.col = [(1.0, 0.0, 0.0, 1.0), (1.0, 0.0, 0.0, 1.0),(0.0, 1.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0),(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)]
		self.batch = batch_for_shader(self.shader, 'LINES', {"pos": self.vertices, "color": self.col})
 
	def draw(self):
		bgl.glLineWidth(5)
		self.shader.bind()
		self.batch.draw(self.shader)
		bgl.glLineWidth(1)

	def doDraw(self):
		global handle
		dns = bpy.app.driver_namespace
		handle = bpy.types.SpaceView3D.draw_handler_add(self.draw, (), 'WINDOW', 'POST_VIEW')
		dns["dc"] = handle



	def stopDraw(self):
		global handle
		if handle is not None:
			bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
     
def RotationOrder(origin):
	order = []
	
	if bpy.context.scene.Wtool_Properties.ViewDirection == 'OP1':
		order.append((origin.x - 2.0, origin.y, origin.z))
		order.append((origin.x, origin.y, origin.z + 2.0))
		order.append((origin.x, origin.y + 2.0, origin.z))
	elif bpy.context.scene.Wtool_Properties.ViewDirection == 'OP2':
		order.append((origin.x + 2.0, origin.y, origin.z))
		order.append((origin.x, origin.y, origin.z - 2.0))
		order.append((origin.x, origin.y + 2.0, origin.z))
	elif bpy.context.scene.Wtool_Properties.ViewDirection == 'OP3':
		order.append((origin.x , origin.y - 2.0, origin.z))
		order.append((origin.x + 2.0, origin.y , origin.z))
		order.append((origin.x, origin.y, origin.z + 2.0))
	elif bpy.context.scene.Wtool_Properties.ViewDirection == 'OP4':
		order.append((origin.x , origin.y + 2.0 , origin.z))
		order.append((origin.x - 2.0, origin.y , origin.z))
		order.append((origin.x, origin.y, origin.z + 2.0))
	elif bpy.context.scene.Wtool_Properties.ViewDirection == 'OP6':
		order.append((origin.x - 2.0, origin.y, origin.z))
		order.append((origin.x, origin.y - 2.0, origin.z))
		order.append((origin.x, origin.y, origin.z + 2.0))
	else:
		order.append((origin.x + 2.0, origin.y, origin.z))
		order.append((origin.x, origin.y + 2.0, origin.z))
		order.append((origin.x, origin.y, origin.z + 2.0))
	return order

	


classes = (
	Wtool_Properties,
	OBJECT_OT_WTool_Helper,
	OBJECT_OT_WTool_Helper2,
	OBJECT_OT_WTool_Helper3,
	OBJECT_OT_WTool_Helper4,
	PANEL_PT_WTool,
)

def register():
	from bpy.utils import register_class
	for cls in classes:
		register_class(cls)
	bpy.types.Scene.Wtool_Properties = bpy.props.PointerProperty(type=Wtool_Properties)
	target: bpy.props.StringProperty(name = 'Target', default = '', description = 'Add object for duplication')
	alignto: bpy.props.StringProperty(name = 'AlignToObject', default = '', description = 'Select an object to correct rotation on duplicates')
	
	
	
	
def unregister():
	from bpy.utils import unregister_class
	for cls in classes:
		unregister_class(cls)
	if len(bpy.app.handlers.depsgraph_update_post) > 0:
		bpy.app.handlers.depsgraph_update_post.remove(selection_change_handler)
if __name__ == "__main__":
	register()

	
	

